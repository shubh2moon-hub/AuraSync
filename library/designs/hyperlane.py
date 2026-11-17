"""Sci-fi corridor: receding chamfered frames with light strips rushing to a vanishing point."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Hyperlane"
DESC = "A deep sci-fi corridor of chamfered frames and racing light strips."
COLOR = "#7a5cff"


def frame(cx, cy, hw, hh, c):
    """Chamfered rectangle outline, closed."""
    return [(cx - hw + c, cy - hh), (cx + hw - c, cy - hh), (cx + hw, cy - hh + c), (cx + hw, cy + hh - c),
            (cx + hw - c, cy + hh), (cx - hw + c, cy + hh), (cx - hw, cy + hh - c), (cx - hw, cy - hh + c),
            (cx - hw + c, cy - hh)]


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    vx, vy = w / 2, h * 0.47
    sc.base = np.zeros((h, w, 3), np.float32) + np.array([0.008, 0.009, 0.014])

    hw0, hh0 = w * 0.62, h * 0.62                  # nearest frame half-size (beyond the screen)
    frames = np.zeros((h, w), np.float32)
    panels = np.zeros((h, w), np.float32)
    n = 26
    prev = None
    for i in range(n):
        z = 1.0 + i * 0.55                          # depth
        hw, hh = hw0 / z, hh0 / z
        c = min(hw, hh) * 0.28
        f = frame(vx, vy, hw, hh, c)
        fade = 1 / (1 + i * 0.12)
        lines(sc, [f], max(1.0, 7 * s / z), fade, frames)
        if prev is not None:   # wall panels between frames: alternate shading
            outer = prev
            polys(sc, [outer[:-1]], 0.5 + 0.5 * (i % 2), panels)
            polys(sc, [f[:-1]], 0.0, panels)
        prev = f
    # rails: lines from the corner of the near frame into the vanishing point
    rails = np.zeros((h, w), np.float32)
    f0 = frame(vx, vy, hw0, hh0, min(hw0, hh0) * 0.28)
    for k, (x, y) in enumerate(f0[:-1]):
        rails = lines(sc, [[(x, y), (vx + (x - vx) * 0.03, vy + (y - vy) * 0.03)]], 2.5 * s, 0.9, rails)
    # light streaks along the floor and ceiling (motion)
    streaks = np.zeros((h, w), np.float32)
    for _ in range(40):
        t0 = sc.rng.uniform(0.05, 0.7)
        L = sc.rng.uniform(0.05, 0.25)
        side = sc.rng.choice([-1, 1])
        ex = sc.rng.uniform(-0.9, 0.9) * hw0
        ey = side * hh0
        p1 = (vx + ex * t0, vy + ey * t0)
        p2 = (vx + ex * min(1.0, t0 + L), vy + ey * min(1.0, t0 + L))
        lines(sc, [[p1, p2]], 2 * s, sc.rng.uniform(0.3, 0.9), streaks)

    depth_dark = np.clip(np.hypot((sc.xx - vx) / w, (sc.yy - vy) / h) * 2.2, 0, 1)
    wall = (0.012 + panels * 0.02) * depth_dark
    sc.base += wall[..., None] * np.array([0.9, 0.95, 1.2])
    sc.base += noise(sc, 1.0 * s, 0.003)[..., None]

    end = np.exp(-(((sc.xx - vx) / (w * 0.02)) ** 2 + ((sc.yy - vy) / (h * 0.02)) ** 2))
    sc.light += glow(frames, s, 0.9, 0.7) * 0.8 + glow(rails, s, 0.8, 0.5) * 0.45 + glow(streaks, s, 0.9, 0.3) * 0.6
    sc.light += end * 0.9 + blur(end, 60 * s) * 2.5
    sc.base += grain(sc, 0.006)
