"""粒子特效系统

修复点:
1. 发射器复用 + 全局发射器/粒子数量上限
2. 渲染排序: 先按距离(近->远), 同距离按透明度(不透明->半透明)
3. 粒子对象池正确回收死亡粒子, 复用时重置全部属性
4. LOD: 远处按距离降密度, 屏幕外直接剔除并暂停更新
5. 生命周期: 发射时长结束自动停止, 粒子支持淡入/淡出
"""
from dataclasses import dataclass, field
from math import hypot

DEFAULT_MAX_EMITTERS = 64
DEFAULT_GLOBAL_MAX_PARTICLES = 50000

# LOD 等级 -> 粒子密度系数; 3 = 屏幕外剔除(完全不生成/不更新)
LOD_DENSITY = {0: 1.0, 1: 0.5, 2: 0.25, 3: 0.0}


@dataclass
class Particle:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    life: float = 1.0
    max_life: float = 1.0
    color: tuple = (255, 255, 255)
    alpha: float = 1.0
    size: float = 1.0
    distance: float = 0.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    active: bool = False

    def reset(self, x=0.0, y=0.0, vx=0.0, vy=0.0, life=1.0,
              color=(255, 255, 255), size=1.0, distance=0.0,
              fade_in=0.0, fade_out=0.0):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.life = float(life)
        self.max_life = float(life)
        self.color = tuple(color)
        self.size = float(size)
        self.distance = float(distance)
        self.fade_in = float(fade_in)
        self.fade_out = float(fade_out)
        # 淡入的粒子初始不可见, 由 update 逐渐提升 alpha
        self.alpha = 0.0 if fade_in > 0.0 else 1.0
        self.active = True


@dataclass
class Emitter:
    eid: str
    particles: list = field(default_factory=list)
    active: bool = True
    emitting: bool = True
    max_particles: int = 1000
    duration: float = float("inf")
    elapsed: float = 0.0
    lod: int = 0
    visible: bool = True
    fade_in: float = 0.0
    fade_out: float = 0.0
    has_emitted: bool = False

    @property
    def alive_count(self) -> int:
        return sum(1 for p in self.particles if p.active)


class ParticleSystem:
    def __init__(self, max_emitters=DEFAULT_MAX_EMITTERS,
                 global_max_particles=DEFAULT_GLOBAL_MAX_PARTICLES):
        self.max_emitters = max_emitters
        self.global_max_particles = global_max_particles
        self.emitters: dict[str, Emitter] = {}
        self.particle_pool: list[Particle] = []
        # LRU 顺序, 用于发射器上限回收
        self._emitter_order: list[str] = []

    # ---------- 发射器 ----------

    def spawn_emitter(self, eid: str, duration: float = float("inf"),
                      max_particles: int = 1000, fade_in: float = 0.0,
                      fade_out: float = 0.0) -> Emitter | None:
        """复用同名发射器; 超过全局上限时回收最旧的非活动发射器。"""
        existing = self.emitters.get(eid)
        if existing is not None:
            existing.active = True
            existing.emitting = True
            existing.visible = True
            existing.elapsed = 0.0
            existing.has_emitted = False
            existing.duration = duration
            existing.fade_in = fade_in
            existing.fade_out = fade_out
            self._emitter_order.remove(eid)
            self._emitter_order.append(eid)
            return existing

        if len(self._emitter_order) >= self.max_emitters:
            victim = self._find_reclaimable_emitter(eid)
            if victim is None:
                return None
            self._remove_emitter(victim)

        emitter = Emitter(eid, duration=duration, max_particles=max_particles,
                          fade_in=fade_in, fade_out=fade_out)
        self.emitters[eid] = emitter
        self._emitter_order.append(eid)
        return emitter

    def _find_reclaimable_emitter(self, new_eid: str) -> str | None:
        for candidate in self._emitter_order:
            if candidate == new_eid:
                continue
            other = self.emitters[candidate]
            if not other.active or other.alive_count == 0:
                return candidate
        return self._emitter_order[0]

    def _remove_emitter(self, eid: str) -> None:
        emitter = self.emitters.pop(eid, None)
        if eid in self._emitter_order:
            self._emitter_order.remove(eid)
        if emitter is not None:
            for particle in emitter.particles:
                if particle.active:
                    self.recycle_particle(particle)
        emitter.particles.clear()

    def stop_emitter(self, eid: str) -> None:
        emitter = self.emitters.get(eid)
        if emitter is not None:
            emitter.emitting = False

    # ---------- 粒子生成 ----------

    def active_particle_count(self) -> int:
        return sum(emitter.alive_count for emitter in self.emitters.values())

    def spawn_particles(self, eid: str, count: int, x: float = 0.0,
                        y: float = 0.0, vx: float = 0.0, vy: float = 0.0,
                        life: float = 1.0, color=(255, 255, 255),
                        size: float = 1.0, distance: float = 0.0,
                        duration: float | None = None,
                        fade_in: float = 0.0,
                        fade_out: float = 0.0) -> list:
        """在(复用的)发射器中生成粒子, 受全局/单发射器上限和 LOD 密度约束。"""
        emitter = self.emitters.get(eid)
        if emitter is None:
            emitter = self.spawn_emitter(
                eid,
                duration=float("inf") if duration is None else duration,
                fade_in=fade_in, fade_out=fade_out)
        if emitter is None or count <= 0:
            return []

        lod = self.calculate_lod(distance, on_screen=True)
        emitter.lod = lod
        count = int(count * LOD_DENSITY[lod])

        global_room = self.global_max_particles - self.active_particle_count()
        emitter_room = emitter.max_particles - emitter.alive_count
        count = max(0, min(count, global_room, emitter_room))

        emitter.has_emitted = True
        spawned = []
        for _ in range(count):
            particle = self._acquire_particle()
            particle.reset(x=x, y=y, vx=vx, vy=vy, life=life, color=color,
                           size=size, distance=distance,
                           fade_in=fade_in or emitter.fade_in,
                           fade_out=fade_out or emitter.fade_out)
            emitter.particles.append(particle)
            spawned.append(particle)
        return spawned

    def _acquire_particle(self) -> Particle:
        if self.particle_pool:
            return self.particle_pool.pop()
        return Particle()

    # ---------- 排序 ----------

    @staticmethod
    def _effective_distance(particle: Particle) -> float:
        return particle.distance if particle.distance > 0 else hypot(
            particle.x, particle.y)

    def sort_particles(self, particles: list) -> list:
        """距离升序(近的先画, 防止远处特效盖住近处), 同距离不透明优先。

        返回新列表, 不修改入参顺序。
        """
        return sorted(particles,
                      key=lambda p: (self._effective_distance(p), -p.alpha))

    # ---------- 对象池 ----------

    def recycle_particle(self, particle: Particle) -> None:
        particle.active = False
        # 防止同一粒子被重复入池 (按对象身份判断, 非字段相等)
        if not any(pooled is particle for pooled in self.particle_pool):
            self._reset_particle_state(particle)
            self.particle_pool.append(particle)

    @staticmethod
    def _reset_particle_state(particle: Particle) -> None:
        particle.x = 0.0
        particle.y = 0.0
        particle.vx = 0.0
        particle.vy = 0.0
        particle.life = 1.0
        particle.max_life = 1.0
        particle.color = (255, 255, 255)
        particle.alpha = 1.0
        particle.size = 1.0
        particle.distance = 0.0
        particle.fade_in = 0.0
        particle.fade_out = 0.0

    # ---------- LOD ----------

    def calculate_lod(self, distance: float, on_screen: bool) -> int:
        """0 全密度, 1 半密度, 2 四分之一密度, 3 屏幕外剔除。"""
        if not on_screen:
            return 3
        if distance < 50:
            return 0
        if distance < 150:
            return 1
        return 2

    # ---------- 更新 / 生命周期 ----------

    def update_emitter(self, eid: str, delta: float,
                       on_screen: bool = True) -> None:
        emitter = self.emitters.get(eid)
        if emitter is None or not emitter.active:
            return

        # 屏幕外: 标记不可见并暂停, 不消耗 CPU 计算玩家看不到的特效
        emitter.visible = on_screen
        if not on_screen or emitter.lod == 3:
            return

        emitter.elapsed += delta
        if emitter.elapsed >= emitter.duration:
            emitter.emitting = False

        survivors = []
        for particle in emitter.particles:
            particle.life -= delta
            if particle.life <= 0:
                self.recycle_particle(particle)
                continue
            particle.x += particle.vx * delta
            particle.y += particle.vy * delta
            particle.alpha = self._compute_alpha(particle)
            survivors.append(particle)
        emitter.particles = survivors

        # 已发射过的发射器, 当前批次粒子全部死亡 -> 生命周期结束
        if emitter.has_emitted and not emitter.particles:
            emitter.emitting = False
            emitter.active = False
        elif not emitter.emitting and not emitter.particles:
            emitter.active = False

    # update_particles 为对外常用别名
    def update_particles(self, eid: str, delta: float,
                         on_screen: bool = True) -> None:
        self.update_emitter(eid, delta, on_screen=on_screen)

    @staticmethod
    def _compute_alpha(particle: Particle) -> float:
        if particle.fade_in > 0.0:
            alpha_in = min(1.0, (particle.max_life - particle.life)
                           / particle.fade_in)
        else:
            alpha_in = 1.0
        if particle.fade_out > 0.0:
            alpha_out = min(1.0, particle.life / particle.fade_out)
        else:
            alpha_out = 1.0
        return max(0.0, min(1.0, min(alpha_in, alpha_out)))
