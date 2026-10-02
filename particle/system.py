"""粒子特效系统 - 含5个bug"""
from dataclasses import dataclass, field

@dataclass
class Particle:
    x: float = 0.0
    y: float = 0.0
    life: float = 1.0
    color: tuple = (255, 255, 255)
    active: bool = False

@dataclass
class Emitter:
    eid: str
    particles: list = field(default_factory=list)
    active: bool = True
    max_particles: int = 1000  # bug1: 无全局上限

class ParticleSystem:
    def __init__(self):
        self.emitters: dict[str, Emitter] = {}
        self.particle_pool: list = []  # bug3: 不回收

    def spawn_emitter(self, eid: str) -> Emitter:
        # bug1: 不复用发射器
        emitter = Emitter(eid)
        self.emitters[eid] = emitter
        return emitter

    def sort_particles(self, particles: list) -> list:
        # bug2: 排序错误
        return particles

    def recycle_particle(self, particle: Particle) -> None:
        # bug3: 不回收不重置
        particle.active = False

    def calculate_lod(self, distance: float, on_screen: bool) -> int:
        # bug4: 屏幕外不减LOD
        if distance < 50:
            return 0
        return 1

    def update_emitter(self, eid: str, delta: float) -> None:
        # bug5: 寿命结束不停止
        emitter = self.emitters.get(eid)
        if emitter:
            for p in emitter.particles:
                p.life -= delta
