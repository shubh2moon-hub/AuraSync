"""Flowing light ribbons drifting across a dark gradient, with bokeh particles."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Flow"
DESC = "Silky ribbons of light flowing through the dark."
COLOR = "#3d7bff"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    sc.base = vgrad(sc, (0.006, 0.008, 0.016), (0.014, 0.01, 0.024), 1.0)
    rib = np.zeros((h, w), np.float32)
    along = w if sc.landscape else h        # ribbons run along the long side
    n_rib = 34
    for i in range(n_rib):
        t = np.linspace(-0.05, 1.05, 700)
        phase = i * 0.09
        amp = 0.16 + 0.04 * np.sin(i * 0.7)
        y = 0.5 + amp * np.sin(t * 2 * np.pi * 0.9 + phase) + 0.08 * np.sin(t * 2 * np.pi * 2.1 + phase * 1.7) \
            + (i - n_rib / 2) * 0.006
        if sc.landscape:
            pts = list(zip(t * w, y * h))
        else:
            pts = list(zip(y * w, t * h))
        core = abs(i - n_rib * 0.45) < 3
        lines(sc, [pts], (2.6 if core else 1.3) * s, 1.0 if core else 0.35 + 0.25 * np.cos(i * 0.4) ** 2, rib)
    # depth: fade ribbons toward the ends
    fade_coord = (sc.xx / w) if sc.landscape else (sc.yy / h)
    fade = np.clip(np.sin(np.clip(fade_coord, 0, 1) * np.pi) * 1.6, 0, 1) ** 0.7
    rib *= fade
    sc.light += glow(rib, s, 0.9, 1.0) * 0.7 + blur(rib, 150 * s) * 0.6

    # bokeh dots
    bok = np.zeros((h, w), np.float32)
    for _ in range(70):
        x, y = sc.rng.uniform(0, w), sc.rng.uniform(0, h)
        r = sc.px(sc.rng.uniform(4, 22))
        polys(sc, [[(x + r * np.cos(a), y + r * np.sin(a)) for a in np.linspace(0, 6.29, 28)]], sc.rng.uniform(0.05, 0.25), bok)
    sc.light += blur(bok, 2 * s)
    sc.base += noise(sc, 200 * s, 0.01)[..., None] * np.array([0.6, 0.5, 1.0])
    sc.base += grain(sc, 0.006)
