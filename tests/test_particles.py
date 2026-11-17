import math

import pytest

from render.particles import (bounce, color_over_life, cull_particles,
                              emission_count, interpolate_position,
                              kill_expired, lifetime_alpha, limit_emission,
                              lod_stride, pack_instances, sort_particles,
                              update_particle)


def test_emission_keeps_fractional_remainder():
    count, remainder = emission_count(10.5, 0.1)
    assert count == 1
    assert remainder == pytest.approx(0.05)


def test_particle_velocity_is_damped_by_drag():
    p = {"x": 0.0, "y": 0.0, "vx": 10.0, "vy": 0.0}
    update_particle(p, 1.0, gravity=0.0, drag=1.0)
    assert p["x"] == pytest.approx(10.0 * math.exp(-1.0), rel=0.01)


def test_gravity_is_integrated_into_velocity():
    p = {"x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0}
    update_particle(p, 0.5, gravity=-2.0, drag=0.0)
    assert p["vy"] == pytest.approx(-1.0)
    assert p["y"] == pytest.approx(-0.5)


def test_alpha_fades_in_at_birth():
    assert lifetime_alpha(0.0, 1.0) == pytest.approx(0.0)


def test_alpha_fades_out_near_death():
    assert lifetime_alpha(0.9, 1.0) == pytest.approx(0.5)


def test_expired_particles_are_removed():
    particles = [{"age": 0.9, "lifetime": 1.0}, {"age": 0.1, "lifetime": 1.0}]
    alive = kill_expired(particles, 0.2)
    assert len(alive) == 1
    assert alive[0]["age"] == pytest.approx(0.3)


def test_instance_buffer_stride_is_eight_floats():
    particles = [{"x": 1, "y": 2, "vx": 3, "vy": 4, "age": 0.5, "r": 1, "g": 0, "b": 0},
                 {"x": 5, "y": 6, "vx": 7, "vy": 8, "age": 0.1, "r": 0, "g": 1, "b": 0}]
    assert len(pack_instances(particles)) == 16


def test_instance_buffer_layout_is_stable():
    particles = [{"x": 1, "y": 2, "vx": 3, "vy": 4, "age": 0.5, "r": 1, "g": 0, "b": 0}]
    assert pack_instances(particles) == [1, 2, 3, 4, 0.5, 1, 0, 0]


def test_sort_is_back_to_front():
    particles = [{"z": 5}, {"z": 1}, {"z": 3}]
    assert [p["z"] for p in sort_particles(particles)] == [5, 3, 1]


def test_cull_drops_particles_outside_bounds():
    particles = [{"x": 5, "y": 5}, {"x": 20, "y": 5}, {"x": 5, "y": -3}]
    assert cull_particles(particles, 0, 10, 0, 10) == [{"x": 5, "y": 5}]


def test_lod_stride_skips_instances_over_budget():
    assert lod_stride(1000, 250) == 4


def test_emission_is_capped_by_capacity():
    assert limit_emission(20, alive=90, capacity=100) == 10


def test_bounce_applies_restitution():
    p = {"x": 0.0, "y": -1.0, "vx": 0.0, "vy": -10.0}
    bounce(p, ground_y=0.0, restitution=0.5)
    assert p["y"] == pytest.approx(0.0)
    assert p["vy"] == pytest.approx(5.0)


def test_interpolation_uses_sub_frame_alpha():
    prev = {"x": 0.0, "y": 0.0}
    curr = {"x": 10.0, "y": 10.0}
    mid = interpolate_position(prev, curr, 0.5)
    assert mid == {"x": 5.0, "y": 5.0}


def test_color_is_interpolated_over_lifetime():
    assert color_over_life(0.5) == pytest.approx((0.5, 0.0, 0.5))

