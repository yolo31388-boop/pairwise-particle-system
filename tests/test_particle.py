"""粒子特效系统 - 测试 (13)"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from particle.system import ParticleSystem, Particle, Emitter


class TestEmitterReuse:
    def test_emitter_reused(self):
        ps = ParticleSystem()
        ps.spawn_emitter("e1")
        ps.spawn_emitter("e1")
        assert len(ps.emitters) == 1

    def test_emitter_global_cap(self):
        ps = ParticleSystem(max_emitters=2)
        ps.spawn_emitter("e1")
        ps.spawn_emitter("e2")
        ps.spawn_emitter("e3")
        assert len(ps.emitters) <= 2


class TestParticleSorting:
    def test_particles_sorted_by_distance(self):
        ps = ParticleSystem()
        particles = [Particle(x=10), Particle(x=5), Particle(x=20)]
        sorted_p = ps.sort_particles(particles)
        assert sorted_p[0].x <= sorted_p[1].x

    def test_particles_sorted_by_alpha_at_same_distance(self):
        ps = ParticleSystem()
        near = Particle(distance=10, alpha=1.0)
        far = Particle(distance=10, alpha=0.2)
        sorted_p = ps.sort_particles([far, near])
        assert sorted_p[0].alpha == 1.0
        assert sorted_p[1].alpha == 0.2


class TestParticleRecycle:
    def test_dead_particles_recycled(self):
        ps = ParticleSystem()
        p = Particle(life=0, active=True)
        ps.recycle_particle(p)
        assert len(ps.particle_pool) == 1

    def test_recycled_particle_attributes_reset(self):
        ps = ParticleSystem()
        p = Particle(x=9, y=8, vx=7, vy=6, life=0, color=(1, 2, 3),
                     alpha=0.3, active=True)
        ps.recycle_particle(p)
        reused = ps.particle_pool[0]
        assert reused.active is False
        assert reused.x == 0 and reused.y == 0
        assert reused.vx == 0 and reused.vy == 0
        assert reused.color == (255, 255, 255)
        assert reused.alpha == 1.0
        assert reused.life == 1.0


class TestGlobalParticleCap:
    def test_global_particle_cap_enforced(self):
        ps = ParticleSystem(global_max_particles=50)
        ps.spawn_particles("e1", 100)
        assert ps.active_particle_count() == 50


class TestOffScreenLOD:
    def test_off_screen_particles_reduced(self):
        ps = ParticleSystem()
        lod = ps.calculate_lod(10, on_screen=False)
        assert lod > 0

    def test_far_effect_lower_lod(self):
        ps = ParticleSystem()
        assert ps.calculate_lod(10, True) < ps.calculate_lod(300, True)

    def test_off_screen_emitter_paused(self):
        ps = ParticleSystem()
        ps.spawn_particles("e1", 5, life=1.0)
        particles = list(ps.emitters["e1"].particles)
        ps.update_emitter("e1", 0.5, on_screen=False)
        assert ps.emitters["e1"].visible is False
        for before, after in zip(particles, ps.emitters["e1"].particles):
            assert after.life == before.life


class TestEmitterLifecycle:
    def test_emitter_stops_when_particles_dead(self):
        ps = ParticleSystem()
        emitter = ps.spawn_emitter("e1")
        emitter.particles = [Particle(life=0)]
        emitter.has_emitted = True
        ps.update_emitter("e1", 0.1)
        assert emitter.active is False

    def test_duration_stops_emission(self):
        ps = ParticleSystem()
        emitter = ps.spawn_emitter("e1", duration=1.0)
        ps.spawn_particles("e1", 1, life=10.0)
        ps.update_emitter("e1", 2.0, on_screen=True)
        assert emitter.emitting is False


class TestFade:
    def test_fade_in_and_fade_out_alpha(self):
        ps = ParticleSystem()
        spawned = ps.spawn_particles("e1", 1, life=1.0,
                                     fade_in=0.2, fade_out=0.2)
        p = spawned[0]
        assert p.alpha == 0.0
        ps.update_emitter("e1", 0.1, on_screen=True)
        mid_alpha = ps.emitters["e1"].particles[0].alpha
        assert 0.0 < mid_alpha < 1.0
        ps.update_emitter("e1", 0.8, on_screen=True)
        end_alpha = ps.emitters["e1"].particles[0].alpha
        assert 0.0 < end_alpha < 1.0
