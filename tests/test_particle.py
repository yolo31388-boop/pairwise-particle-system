"""粒子特效系统 - 红态测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from particle.system import ParticleSystem, Particle


class TestEmitterReuse:
    def test_emitter_reused(self):
        ps = ParticleSystem()
        first = ps.spawn_emitter("e1")
        second = ps.spawn_emitter("e1")
        assert first is second
        assert len(ps.emitters) == 1

    def test_emitter_count_capped(self):
        ps = ParticleSystem(max_emitters=2)
        ps.spawn_particles("e1", 1)
        ps.spawn_particles("e2", 1)
        ps.spawn_particles("e3", 1)
        assert len(ps.emitters) == 2
        assert "e1" not in ps.emitters


class TestGlobalParticleCap:
    def test_global_particle_cap(self):
        ps = ParticleSystem(max_particles=10)
        spawned = ps.spawn_particles("e1", 50)
        assert len(spawned) == 10
        assert ps._active_particle_count() == 10


class TestParticleSorting:
    def test_particles_sorted_by_distance(self):
        ps = ParticleSystem()
        particles = [Particle(x=10), Particle(x=5), Particle(x=20)]
        sorted_p = ps.sort_particles(particles)
        assert sorted_p[0].x <= sorted_p[1].x
        assert sorted_p[0].x == 5

    def test_particles_sorted_by_alpha_at_same_distance(self):
        ps = ParticleSystem()
        faint = Particle(x=0, y=0, alpha=0.5)
        solid = Particle(x=0, y=0, alpha=1.0)
        sorted_p = ps.sort_particles([faint, solid])
        assert sorted_p[0].alpha == 1.0
        assert sorted_p[1].alpha == 0.5


class TestParticleRecycle:
    def test_dead_particles_recycled(self):
        ps = ParticleSystem()
        p = Particle(life=0, active=True)
        ps.recycle_particle(p)
        assert len(ps.particle_pool) == 1

    def test_recycled_particle_reset_and_reused(self):
        ps = ParticleSystem()
        p = Particle(life=5.0, color=(1, 2, 3), vx=9.0,
                     vy=8.0, active=True)
        ps.recycle_particle(p)
        assert p.vx == 0.0
        assert p.vy == 0.0
        assert p.color == (255, 255, 255)
        assert p.life == 0.0

        reused = ps.acquire_particle(life=1.0)
        assert reused is p
        assert reused.active is True
        assert reused.life == 1.0
        assert reused.color == (255, 255, 255)
        assert len(ps.particle_pool) == 0


class TestOffScreenLOD:
    def test_off_screen_particles_reduced(self):
        ps = ParticleSystem()
        lod = ps.calculate_lod(10, on_screen=False)
        assert lod > 0

        assert ps.calculate_lod(10, True) == 0
        assert ps.calculate_lod(100, True) == 1
        assert ps.calculate_lod(200, True) == 2
        assert ps.calculate_lod(500, True) == 3

    def test_lod_scales_particle_count(self):
        ps = ParticleSystem(max_particles=10000)
        near = ps.spawn_particles("near", 100)
        assert len(near) == 100
        far = ps.spawn_emitter("far")
        far.lod = 2
        far_particles = ps.spawn_particles("far", 100)
        assert len(far_particles) == 33

    def test_off_screen_emitter_paused(self):
        ps = ParticleSystem()
        ps.spawn_particles("e1", 1, life=5.0)
        emitter = ps.emitters["e1"]
        emitter.on_screen = False
        before = emitter.particles[0].life
        ps.update_emitter("e1", 1.0)
        assert emitter.particles[0].life == before


class TestEmitterLifecycle:
    def test_emitter_stops_when_particles_dead(self):
        ps = ParticleSystem()
        emitter = ps.spawn_emitter("e1")
        emitter.particles = [Particle(life=0)]
        ps.update_emitter("e1", 0.1)
        assert emitter.active is False

    def test_emitter_stops_emitting_after_duration(self):
        ps = ParticleSystem()
        emitter = ps.spawn_emitter("e1", duration=0.5)
        ps.spawn_particles("e1", 5, life=0.4)
        ps.update_emitter("e1", 0.6)
        assert emitter.emitting is False
        assert emitter.active is False
        assert ps.spawn_particles("e1", 5) == []

    def test_particles_fade_in_and_out(self):
        ps = ParticleSystem()
        spawned = ps.spawn_particles("e1", 1, life=2.0,
                                     fade_in=0.5, fade_out=0.5)
        particle = spawned[0]
        assert particle.alpha == 0.0

        ps.update_emitter("e1", 0.25)
        assert abs(particle.alpha - 0.5) < 1e-6

        ps.update_emitter("e1", 1.6)
        assert abs(particle.alpha - 0.3) < 1e-6

        ps.update_emitter("e1", 0.2)
        assert ps.emitters["e1"].particles == []
        assert len(ps.particle_pool) == 1
