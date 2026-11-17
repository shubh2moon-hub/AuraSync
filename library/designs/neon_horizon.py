"""Synthwave sunset: striped sun, wireframe mountains and a perspective grid floor."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Neon Horizon"
DESC = "Retro sunset with a striped sun, wireframe mountains and an endless grid."
COLOR = "#ff2fb4"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    hz = h * (0.56 if sc.landscape else 0.58)          # horizon
    cx = w / 2

    # sky + floor base
    sky = vgrad(sc, (0.015, 0.012, 0.05), (0.09, 0.025, 0.11), 1.6)
    floor = vgrad(sc, (0.02, 0.01, 0.04), (0.005, 0.004, 0.012), 0.6)
    below = (sc.yy > hz)[..., None]
    sc.base = np.where(below, floor, sky)

    # stars
    n = int(w * h / 9000)
    xs, ys = sc.rng.uniform(0, w, n), sc.rng.uniform(0, hz * 0.9, n)
    st = np.zeros((h, w), np.float32)
    st[ys.astype(int), xs.astype(int)] = sc.rng.uniform(0.2, 0.9, n) ** 2
    st = blur(st, 0.7 * s) * 3
    sc.base += st[..., None] * np.array([0.8, 0.85, 1.0]) * (1 - sc.yy[..., None] / hz).clip(0, 1)

    # sun: vertical gradient disc with stripe gaps in its lower half
    r = (0.24 if sc.landscape else 0.36) * min(w, h) * (1.0 if sc.landscape else 1.15)
    sy = hz - r * 0.38
    d = np.sqrt((sc.xx - cx) ** 2 + (sc.yy - sy) ** 2)
    disc = np.clip((r - d) / (1.2 * s), 0, 1)
    rel = (sc.yy - sy) / r                                # -1 top .. 1 bottom
    stripes = np.ones_like(disc)
    edge_px = 1.5 * s / r
    for i in range(7):
        y0 = -0.32 + i * 0.105                            # visible part of the sun is rel < 0.38
        gap = 0.006 + i * 0.0065                          # gaps widen toward the bottom
        stripes *= np.clip((np.abs(rel - y0) - gap) / edge_px, 0, 1)
    sun = disc * stripes * (sc.yy < hz)
    sun_val = sun * (0.32 + 0.38 * np.clip(0.55 - rel * 0.6, 0, 1))
    sc.base += sun[..., None] * np.array([0.06, 0.015, 0.05])
    sc.light += sun_val + blur(sun, 40 * s) * 0.25 + blur(sun, 160 * s) * 0.2

    # mountains: two ridges of jagged peaks in front of the sun, wireframe edges lit
    rid = []
    for layer, (height, dark, lit) in enumerate([(0.30, 0.05, 0.55), (0.18, 0.025, 0.9)]):
        k = 22 if sc.landscape else 10
        xs = np.linspace(-0.05 * w, 1.05 * w, k)
        peak = hz - sc.rng.uniform(0.25, 1.0, k) * height * h * (0.55 if sc.landscape else 0.35)
        peak[0] = peak[-1] = hz
        # keep the sun visible in the middle for the front ridge
        if layer == 1:
            mid = np.abs(xs - cx) < r * 0.9
            peak[mid] = hz - (hz - peak[mid]) * 0.25
        pts = list(zip(xs, peak)) + [(1.05 * w, hz + 2), (-0.05 * w, hz + 2)]
        m = polys(sc, [pts])
        shade = vgrad(sc, (dark * 0.5, dark * 0.3, dark * 1.6), (dark * 0.2, dark * 0.1, dark * 0.8))
        sc.base = sc.base * (1 - m[..., None]) + shade * m[..., None]
        sc.light *= 1 - m
        edge = lines(sc, [list(zip(xs, peak))], 2.2 * s)
        # inner wireframe: lines from each peak down to the valley between neighbours
        wf = []
        for i in range(1, k - 1):
            wf.append([(xs[i], peak[i]), ((xs[i] + xs[i + 1]) / 2, hz)])
            wf.append([(xs[i], peak[i]), ((xs[i] + xs[i - 1]) / 2, hz)])
        inner = lines(sc, wf, 1.1 * s) * 0.35
        rid.append((edge + inner) * lit)
    for rr in rid:
        sc.light += glow(rr, s, 0.8, 0.6) * 0.8

    # grid floor
    g = np.zeros((h, w), np.float32)
    depth = h - hz
    vert = []
    span = 26 if sc.landscape else 14
    for i in range(-span, span + 1):
        x_far = cx + i * w * 0.012
        x_near = cx + i * w * (0.11 if sc.landscape else 0.2)
        vert.append([(x_far, hz), (x_near, h * 1.05)])
    lines(sc, vert, 1.6 * s, 1.0, g)
    horiz, last = [], hz
    for j in range(1, 40):
        y = hz + depth * ((j / 39) ** 1.9)
        if y - last < 11 * s and j < 39:      # too dense near the horizon: skip to avoid shimmer
            continue
        horiz.append([(0, y), (w, y)])
        last = y
    lines(sc, horiz, 1.6 * s, 1.0, g)
    fade = np.clip((sc.yy - hz) / (depth * 0.45), 0, 1) ** 1.3
    g *= fade * (sc.yy > hz)
    sc.light += glow(g, s, 0.9, 0.5) * 0.75

    # horizon line + sun reflection on the floor
    hzl = lines(sc, [[(0, hz), (w, hz)]], 2.5 * s)
    sc.light += glow(hzl, s, 1.2, 1.4)
    ref = np.zeros_like(sun)
    rows = np.arange(h)
    src = (2 * hz - rows).astype(int)
    ok = (rows > hz) & (src >= 0) & (src < h)
    ref[ok] = sun_val[src[ok]]
    ref = blur(ref, 6 * s)
    ref *= np.clip(1 - (sc.yy - hz) / (depth * 0.9), 0, 1)
    sc.light += blur(ref, 3 * s) * 0.18

    # haze over the horizon
    haze = np.exp(-((sc.yy - hz) / (0.06 * h)) ** 2)
    sc.light += haze * 0.08
    sc.base += haze[..., None] * np.array([0.03, 0.01, 0.05])
    sc.base += grain(sc, 0.008)
