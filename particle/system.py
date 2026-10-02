"""粒子特效系统

修复点:
1. 发射器按 eid 复用, 发射器数量与全局存活粒子数均有上限
2. 渲染按距离(近 -> 远)排序, 同距离按透明度(不透明 -> 透明)排序
3. 粒子对象池回收死亡粒子, 复用时完全重置属性
4. 按距离/屏幕内外计算 LOD, 屏幕外的发射器暂停更新
5. 发射器到时停止发射, 粒子支持淡入淡出, 粒子全部死亡后发射器自动停用
"""
from dataclasses import dataclass, field
from math import hypot

MAX_EMITTERS = 128
MAX_PARTICLES_GLOBAL = 10000


@dataclass
class Particle:
    x: float = 0.0
    y: float = 0.0
    life: float = 1.0
    max_life: float = 1.0
    vx: float = 0.0
    vy: float = 0.0
    color: tuple = (255, 255, 255)
    alpha: float = 1.0
    active: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0


@dataclass
class Emitter:
    eid: str
    particles: list = field(default_factory=list)
    active: bool = True
    emitting: bool = True
    max_particles: int = 1000
    duration: float = -1.0
    lod: int = 0
    on_screen: bool = True
    age: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0


class ParticleSystem:
    def __init__(self, max_emitters: int = MAX_EMITTERS,
                 max_particles: int = MAX_PARTICLES_GLOBAL):
        self.emitters: dict[str, Emitter] = {}
        self.particle_pool: list = []
        self.max_emitters = max_emitters
        self.max_particles = max_particles
        self._emitter_order: list[str] = []

    # ---------- 发射器: 复用 + 数量上限 ----------

    def spawn_emitter(self, eid: str, duration: float = -1.0,
                      max_particles: int = 1000,
                      fade_in: float = 0.2, fade_out: float = 0.3) -> Emitter:
        existing = self.emitters.get(eid)
        if existing is not None:
            return existing

        if len(self.emitters) >= self.max_emitters:
            victim = None
            for key in self._emitter_order:
                candidate = self.emitters.get(key)
                if candidate is not None and not candidate.active:
                    victim = key
                    break
            if victim is None and self._emitter_order:
                victim = self._emitter_order[0]
            if victim is None:
                return None
            self._remove_emitter(victim)

        emitter = Emitter(eid, duration=duration, max_particles=max_particles,
                          fade_in=fade_in, fade_out=fade_out)
        self.emitters[eid] = emitter
        self._emitter_order.append(eid)
        return emitter

    def _remove_emitter(self, eid: str) -> None:
        emitter = self.emitters.pop(eid, None)
        if eid in self._emitter_order:
            self._emitter_order.remove(eid)
        if emitter:
            for particle in emitter.particles:
                self.recycle_particle(particle)

    def _active_particle_count(self) -> int:
        return sum(len(emitter.particles) for emitter in self.emitters.values())

    # ---------- 粒子池: 回收 + 重置 ----------

    def _reset_particle(self, particle: Particle, x, y, life, color,
                        vx, vy, fade_in, fade_out) -> None:
        particle.x = x
        particle.y = y
        particle.vx = vx
        particle.vy = vy
        particle.life = life
        particle.max_life = life
        particle.color = color
        particle.fade_in = fade_in
        particle.fade_out = fade_out
        particle.alpha = 0.0 if fade_in > 0.0 else 1.0
        particle.active = True

    def acquire_particle(self, x: float = 0.0, y: float = 0.0,
                         life: float = 1.0, color: tuple = (255, 255, 255),
                         vx: float = 0.0, vy: float = 0.0,
                         fade_in: float = 0.0,
                         fade_out: float = 0.0) -> Particle:
        if self.particle_pool:
            particle = self.particle_pool.pop()
        else:
            particle = Particle()
        self._reset_particle(particle, x, y, life, color, vx, vy,
                             fade_in, fade_out)
        return particle

    def recycle_particle(self, particle: Particle) -> None:
        particle.active = False
        particle.x = 0.0
        particle.y = 0.0
        particle.vx = 0.0
        particle.vy = 0.0
        particle.life = 0.0
        particle.max_life = 0.0
        particle.alpha = 0.0
        particle.color = (255, 255, 255)
        particle.fade_in = 0.0
        particle.fade_out = 0.0
        if not any(p is particle for p in self.particle_pool):
            self.particle_pool.append(particle)

    # ---------- 发射: 全局粒子上限 + LOD 减量 ----------

    def spawn_particles(self, eid: str, count: int, life: float = 1.0,
                        color: tuple = (255, 255, 255), speed: float = 0.0,
                        x: float = 0.0, y: float = 0.0,
                        fade_in: float = None,
                        fade_out: float = None) -> list:
        emitter = self.spawn_emitter(eid)
        if emitter is None or not emitter.emitting:
            return []
        emitter.active = True

        if fade_in is None:
            fade_in = emitter.fade_in
        if fade_out is None:
            fade_out = emitter.fade_out

        count = max(0, int(count / (emitter.lod + 1)))
        capacity = min(
            emitter.max_particles - len(emitter.particles),
            self.max_particles - self._active_particle_count(),
        )
        count = max(0, min(count, capacity))

        spawned = []
        for index in range(count):
            vx = speed * (0.9 if index % 2 == 0 else -0.9)
            vy = speed * (0.7 if index % 3 == 0 else -0.7)
            particle = self.acquire_particle(
                x=x, y=y, life=life, color=color, vx=vx, vy=vy,
                fade_in=fade_in, fade_out=fade_out)
            emitter.particles.append(particle)
            spawned.append(particle)
        return spawned

    # ---------- 排序: 距离近->远, 同距离不透明->透明 ----------

    def sort_particles(self, particles: list) -> list:
        return sorted(particles,
                      key=lambda p: (hypot(p.x, p.y),
                                     -getattr(p, "alpha", 1.0)))

    # ---------- LOD ----------

    def calculate_lod(self, distance: float, on_screen: bool) -> int:
        if not on_screen:
            return 3
        if distance < 50:
            return 0
        if distance < 150:
            return 1
        if distance < 300:
            return 2
        return 3

    def set_emitter_visibility(self, eid: str, distance: float,
                               on_screen: bool) -> None:
        emitter = self.emitters.get(eid)
        if emitter:
            emitter.lod = self.calculate_lod(distance, on_screen)
            emitter.on_screen = on_screen

    # ---------- 生命周期: 到时停发 + 淡入淡出 + 粒子回收 ----------

    @staticmethod
    def _compute_alpha(particle: Particle) -> float:
        if particle.max_life <= 0.0:
            return 1.0
        elapsed = particle.max_life - particle.life
        alpha = 1.0
        if particle.fade_in > 0.0:
            alpha = min(alpha, elapsed / particle.fade_in)
        if particle.fade_out > 0.0:
            alpha = min(alpha,
                        max(0.0, particle.life) / particle.fade_out)
        return max(0.0, min(1.0, alpha))

    def update_emitter(self, eid: str, delta: float) -> None:
        emitter = self.emitters.get(eid)
        if not emitter or not emitter.active:
            return
        if not emitter.on_screen:
            return

        emitter.age += delta
        if emitter.duration >= 0.0 and emitter.age >= emitter.duration:
            emitter.emitting = False

        had_particles = bool(emitter.particles)
        alive = []
        for particle in emitter.particles:
            particle.life -= delta
            if particle.life > 0.0:
                particle.x += particle.vx * delta
                particle.y += particle.vy * delta
                particle.alpha = self._compute_alpha(particle)
                alive.append(particle)
            else:
                self.recycle_particle(particle)
        emitter.particles = alive

        if not emitter.particles and (had_particles or not emitter.emitting):
            emitter.active = False
