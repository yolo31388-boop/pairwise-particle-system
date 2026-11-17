"""CPU-side helpers for the GPU particle system.

The functions here are deliberately small and stateless so the simulation
step can be driven by the renderer at whatever frame rate the device runs at.
Time is always the unit of progress: emission carries its fractional remainder
between frames, velocities are integrated with gravity and drag, and rendering
data is packed in a fixed 8-float instance stride.
"""

import math


# Number of floats written per particle in the GPU instance buffer:
# x, y, vx, vy, age, r, g, b.
INSTANCE_STRIDE = 8


def emission_count(rate, dt, accumulator=0.0):
    """Return ``(new_particles, remainder)`` for one time step.

    ``rate`` is particles per second and ``dt`` is the frame's duration in
    seconds.  The fractional part of the computed amount is returned and must
    be fed back in as ``accumulator`` on the next frame; otherwise low frame
    rates silently lose particles and high frame rates can round differently.
    """
    if rate <= 0.0 or dt <= 0.0:
        remainder = max(0.0, accumulator)
        return 0, remainder

    total = rate * dt + accumulator
    count = int(math.floor(total))
    return count, total - count


def update_particle(particle, dt, gravity=-9.8, drag=0.0):
    """Advance one particle by ``dt`` seconds.

    Velocity is damped exponentially (``v *= exp(-drag * dt)``), gravity is
    integrated into vertical velocity, and the new velocity is used to move the
    particle.  Exponential damping keeps the result stable for large ``dt``
    instead of exploding with an explicit ``v -= drag * v * dt`` step.
    """
    if dt <= 0.0:
        return particle

    vx = particle["vx"]
    vy = particle["vy"]

    if drag > 0.0:
        damping = math.exp(-drag * dt)
        vx *= damping
        vy *= damping

    vy += gravity * dt

    particle["x"] += vx * dt
    particle["y"] += vy * dt
    particle["vx"] = vx
    particle["vy"] = vy
    return particle


def lifetime_alpha(age, lifetime, fade_in=0.1, fade_out=0.8):
    """Opacity for a particle at ``age`` seconds of a ``lifetime``-second life.

    ``fade_in`` and ``fade_out`` are fractions of the lifetime: the particle
    fades in over the first ``fade_in`` of its life and starts fading out when
    the remaining life reaches ``1 - fade_out``.  Returns a value in [0, 1].
    """
    if lifetime <= 0.0 or age <= 0.0 or age >= lifetime:
        return 0.0

    t = age / lifetime
    alpha = 1.0

    if fade_in > 0.0:
        alpha = min(alpha, t / fade_in)

    fade_out_start = fade_out
    if fade_out_start < 1.0:
        alpha = min(alpha, (1.0 - t) / (1.0 - fade_out_start))

    return max(0.0, min(1.0, alpha))


def kill_expired(particles, dt):
    """Advance ages by ``dt`` and return a new list of still-living particles.

    Expired entries are left out of the returned list so the caller can return
    them to its pool; their state is reset there before reuse.
    """
    alive = []
    for particle in particles:
        age = particle.get("age", 0.0) + dt
        particle["age"] = age

        lifetime = particle.get("lifetime")
        if lifetime is None or age < lifetime:
            alive.append(particle)

    return alive


def pack_instances(particles):
    """Flatten particles into the GPU instance buffer layout.

    Every particle occupies exactly :data:`INSTANCE_STRIDE` floats:
    ``x, y, vx, vy, age, r, g, b``.  A stable stride is required by the vertex
    shader; packing a variable number of floats would misalign every particle
    after the first.
    """
    data = []
    for particle in particles:
        data.extend([
            particle.get("x", 0.0),
            particle.get("y", 0.0),
            particle.get("vx", 0.0),
            particle.get("vy", 0.0),
            particle.get("age", 0.0),
            particle.get("r", 0.0),
            particle.get("g", 0.0),
            particle.get("b", 0.0),
        ])
    return data


def sort_particles(particles, camera_z=0.0):
    """Return particles sorted back-to-front (largest depth first).

    Alpha blending is order-dependent, so translucent particles must be drawn
    from the far end of the view towards the camera.  Sorting a copy leaves the
    simulation order (and therefore determinism) untouched.
    """
    return sorted(particles,
                  key=lambda p: p.get("z", 0.0) - camera_z,
                  reverse=True)


def cull_particles(particles, xmin, xmax, ymin, ymax):
    """Drop particles outside the inclusive view bounds."""
    return [
        particle for particle in particles
        if xmin <= particle.get("x", 0.0) <= xmax
        and ymin <= particle.get("y", 0.0) <= ymax
    ]


def lod_stride(count, max_instances):
    """Return how many particles to skip per drawn instance.

    When there are more particles than the draw budget allows, draw every
    ``n``-th instance so the visual density degrades smoothly instead of the
    budget being exceeded.  ``1`` means draw everything.
    """
    if count <= 0 or max_instances <= 0 or count <= max_instances:
        return 1
    return int(math.ceil(count / float(max_instances)))


def limit_emission(requested, alive, capacity):
    """Clamp a new-particle request to the free space in the pool."""
    room = max(0, capacity - alive)
    return max(0, min(requested, room))


def bounce(particle, ground_y=0.0, restitution=0.5):
    """Resolve a particle that has moved below the ground plane.

    The particle is placed on the surface and its downward vertical velocity
    is reflected and scaled by ``restitution``; particles above the ground are
    left untouched.
    """
    if particle.get("y", 0.0) < ground_y:
        particle["y"] = ground_y
        vy = particle.get("vy", 0.0)
        if vy < 0.0:
            particle["vy"] = -vy * restitution
    return particle


def interpolate_position(previous, current, alpha):
    """Interpolate a particle's position between two simulation frames.

    ``alpha`` is the fraction of the time step elapsed since ``previous``;
    using it prevents fast particles from visibly teleporting at low render
    frame rates.
    """
    alpha = max(0.0, min(1.0, alpha))
    result = dict(current)
    result["x"] = previous.get("x", 0.0) + (
        current.get("x", 0.0) - previous.get("x", 0.0)) * alpha
    result["y"] = previous.get("y", 0.0) + (
        current.get("y", 0.0) - previous.get("y", 0.0)) * alpha
    return result


def color_over_life(t, start=(1.0, 0.0, 0.0), end=(0.0, 0.0, 1.0)):
    """Linearly interpolate a colour from ``start`` to ``end`` over life ``t``."""
    t = max(0.0, min(1.0, t))
    return tuple(
        start_channel + (end_channel - start_channel) * t
        for start_channel, end_channel in zip(start, end)
    )
