"""粒子特效系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from particle.system import ParticleSystem, Particle, Emitter

class TestEmitterReuse:
    def test_emitter_reused(self):
        ps = ParticleSystem()
        ps.spawn_emitter("e1")
        ps.spawn_emitter("e1")
        assert len(ps.emitters) == 1

class TestParticleSorting:
    def test_particles_sorted_by_distance(self):
        ps = ParticleSystem()
        particles = [Particle(x=10), Particle(x=5), Particle(x=20)]
        sorted_p = ps.sort_particles(particles)
        assert sorted_p[0].x <= sorted_p[1].x

class TestParticleRecycle:
    def test_dead_particles_recycled(self):
        ps = ParticleSystem()
        p = Particle(life=0, active=True)
        ps.recycle_particle(p)
        assert len(ps.particle_pool) == 1

class TestOffScreenLOD:
    def test_off_screen_particles_reduced(self):
        ps = ParticleSystem()
        lod = ps.calculate_lod(10, on_screen=False)
        assert lod > 0

class TestEmitterLifecycle:
    def test_emitter_stops_when_particles_dead(self):
        ps = ParticleSystem()
        emitter = ps.spawn_emitter("e1")
        emitter.particles = [Particle(life=0)]
        ps.update_emitter("e1", 0.1)
        assert emitter.active == False
