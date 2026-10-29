"""Pure-Python point-cloud geometry for MYRA's native hologram.

The same deterministic sample list is evaluated as CORE, MALE and FEMALE
forms, so character changes morph in place.  Faces are smooth silhouettes
only: no carved eyes, lips, scan rings or pedestal geometry are generated.
"""
from __future__ import annotations

import math


def _frac(value):
    return value - math.floor(value)


def _smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def build_samples(count=2800, seed=20261029):
    samples = []
    count = max(300, int(count))
    for index in range(count):
        fraction = (index + 0.5) / count
        if fraction < 0.42:
            part = "head"
            local = fraction / 0.42
        elif fraction < 0.53:
            part = "neck"
            local = (fraction - 0.42) / 0.11
        else:
            part = "torso"
            local = (fraction - 0.53) / 0.47
        samples.append(
            {
                "index": index,
                "fraction": fraction,
                "part": part,
                "local": local,
                "a": _frac((index + 1) * 0.6180339887498949 + seed * 0.000001),
                "b": _frac((index + 1) * 0.7548776662466927 + seed * 0.000003),
                "c": _frac((index + 1) * 0.5698402909980532 + seed * 0.000007),
            }
        )
    return samples


def _sphere(sample, radius=0.84):
    # Deterministic Fibonacci-like sphere using the global sample fraction.
    y = 1.0 - 2.0 * sample["fraction"]
    ring = math.sqrt(max(0.0, 1.0 - y * y))
    theta = sample["index"] * 2.399963229728653
    local_radius = radius * (0.78 + 0.22 * sample["c"])
    return (
        math.cos(theta) * ring * local_radius,
        y * local_radius,
        math.sin(theta) * ring * local_radius,
    )


def _head_point(sample, female=False):
    y_unit = 1.0 - 2.0 * sample["local"]
    ring = math.sqrt(max(0.0, 1.0 - y_unit * y_unit))
    theta = sample["index"] * 2.399963229728653
    x_unit = math.cos(theta) * ring
    z_unit = math.sin(theta) * ring

    if female:
        rx, ry, rz, cy = 0.315, 0.42, 0.335, 0.51
    else:
        rx, ry, rz, cy = 0.335, 0.44, 0.355, 0.52

    x, y, z = x_unit * rx, cy + y_unit * ry, z_unit * rz

    if female:
        # A smooth hair silhouette: expand crown/back and let the sides
        # fall lower.  This stays a silhouette treatment, not facial detail.
        crown = _smoothstep((y_unit + 0.15) / 1.15)
        back = _smoothstep((-z_unit + 0.15) / 1.15)
        side = _smoothstep((abs(x_unit) - 0.35) / 0.65)
        x *= 1.0 + 0.10 * crown + 0.05 * back
        z *= 1.0 + 0.08 * crown + 0.12 * back
        if z_unit < 0.35:
            y -= 0.22 * side * _smoothstep((0.35 - y_unit) / 1.0)
    return x, y, z


def _neck_point(sample, female=False):
    theta = sample["a"] * math.tau
    top = sample["local"]
    rx, rz = (0.095, 0.082) if female else (0.12, 0.105)
    y = 0.0 + top * 0.24
    return math.cos(theta) * rx, y, math.sin(theta) * rz


def _superellipse(theta, exponent=2.7):
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    power = 2.0 / exponent
    x = math.copysign(abs(cos_t) ** power, cos_t)
    z = math.copysign(abs(sin_t) ** power, sin_t)
    return x, z


def _torso_point(sample, female=False):
    theta = sample["a"] * math.tau
    top = sample["local"]  # 0 bottom, 1 shoulders
    y = -0.86 + top * 0.84

    # Continuous S-curve from lower chest to the shoulder line.  The lower
    # chest stays broad (about 82% of shoulder width, like a real chest-up
    # cut) instead of collapsing into a narrow column, which previously
    # read as a chess piece / statue stem.
    rise = _smoothstep((top - 0.04) / 0.92)
    if female:
        width = 0.55 + 0.11 * rise
        depth = 0.205 + 0.05 * top
    else:
        width = 0.66 + 0.14 * rise
        depth = 0.225 + 0.065 * top

    # Slightly rounded lower cut so the bust ends like a torso, not a base.
    bottom_round = 0.90 + 0.10 * _smoothstep(top / 0.10)
    width *= bottom_round
    depth *= bottom_round

    x_unit, z_unit = _superellipse(theta)
    x, z = x_unit * width, z_unit * depth

    # Gentle anatomical shaping without detailed features: a broad front
    # chest plane and naturally sloped shoulders (the outer shoulder line
    # falls away instead of forming a flat horizontal shelf).
    front = max(0.0, z_unit)
    z += front * 0.025 * math.sin(math.pi * min(1.0, top * 1.15))
    if top > 0.80:
        y -= (abs(x_unit) ** 1.6) * 0.15 * _smoothstep((top - 0.80) / 0.20)
        # Neckline: near the top, the front/back centre rises and tucks in
        # toward the neck so the chest flows into the neck (clavicle line)
        # instead of ending in a flat "bell rim" across the whole width.
        neckline = _smoothstep((top - 0.80) / 0.20)
        centre = 1.0 - abs(x_unit)
        y += neckline * centre * 0.10
        x *= 1.0 - 0.10 * neckline * centre
        z *= 1.0 - 0.38 * neckline * centre
    return x, y, z


def point_for(sample, form):
    form = str(form or "core").lower()
    if form == "core":
        return _sphere(sample)
    female = form == "female"
    if sample["part"] == "head":
        return _head_point(sample, female=female)
    if sample["part"] == "neck":
        return _neck_point(sample, female=female)
    return _torso_point(sample, female=female)


def build_point_clouds(count=2800, seed=20261029):
    samples = build_samples(count=count, seed=seed)
    return {
        form: [point_for(sample, form) for sample in samples]
        for form in ("core", "male", "female")
    }, samples


def interpolate(a, b, amount):
    amount = max(0.0, min(1.0, amount))
    return (
        a[0] + (b[0] - a[0]) * amount,
        a[1] + (b[1] - a[1]) * amount,
        a[2] + (b[2] - a[2]) * amount,
    )
