"""Beveled hexagon armour plating with lit seams that intensify toward a glowing core."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Hex Core"
DESC = "Dark hexagon plating with energised seams around a glowing core."
COLOR = "#ff6a00"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    R = sc.px(64)                                # hex radius
    core = (w * (0.68 if sc.landscape else 0.5), h * (0.45 if sc.landscape else 0.42))
    sc.base = vgrad(sc, (0.02, 0.021, 0.026), (0.01, 0.01, 0.013))

    seams = np.zeros((h, w), np.float32)
    plates = np.zeros((h, w), np.float32)
    fills = np.zeros((h, w), np.float32)
    dx, dy = R * np.sqrt(3), R * 1.5
    maxd = np.hypot(w, h) * 0.55
    for row in range(-1, int(h / dy) + 2):
        for col in range(-1, int(w / dx) + 2):
            cx = col * dx + (dx / 2 if row % 2 else 0)
            cy = row * dy
            ang = np.pi / 6 + np.arange(7) * np.pi / 3
            outer = [(cx + R * np.cos(a), cy + R * np.sin(a)) for a in ang]
            inner = [(cx + R * 0.86 * np.cos(a), cy + R * 0.86 * np.sin(a)) for a in ang]
            d = np.hypot(cx - core[0], cy - core[1]) / maxd
            near = np.clip(1 - d * 1.6, 0, 1)
            # plate brightness: subtle per-tile variation, lit from top-left
            polys(sc, [inner], 0.5 + 0.5 * sc.rng.random(), plates)
            # seams: more of them lit near the core
            p = 0.18 + 0.75 * near
            for k in range(6):
                if sc.rng.random() < p:
                    lines(sc, [[outer[k], outer[k + 1]]], 2.2 * s, 0.35 + 0.65 * near, seams)
            if sc.rng.random() < 0.10 + 0.4 * near ** 2:
                polys(sc, [inner], 0.25 + 0.5 * near * sc.rng.random(), fills)

    # bevel shading: emboss-like light from the top-left
    import cv2
    pl = blur(plates, 1.5 * s)
    gx = cv2.Sobel(pl, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(pl, cv2.CV_32F, 0, 1, ksize=3)
    bevel = np.clip(-(gx + gy) * 0.25, -0.5, 0.5)
    metal = 0.03 + pl * 0.025 + bevel * 0.05 + noise(sc, 0.8 * s, 0.004)
    sc.base = np.clip(sc.base + metal[..., None] * np.array([0.95, 1.0, 1.15]), 0, 1)

    # the core: bright hex rings
    cr = np.zeros((h, w), np.float32)
    for k, rr in enumerate([R * 0.9, R * 1.7, R * 2.6]):
        ang = np.arange(7) * np.pi / 3 + np.pi / 6
        lines(sc, [[(core[0] + rr * np.cos(a), core[1] + rr * np.sin(a)) for a in ang]], (3.5 - k) * s, 1.0 - k * 0.25, cr)
    dcore = np.hypot(sc.xx - core[0], sc.yy - core[1])
    heart = np.clip(1 - dcore / (R * 0.75), 0, 1) ** 1.5

    sc.light += glow(seams, s, 0.9, 0.6) * 0.75 + fills * 0.35 + blur(fills, 20 * s) * 0.3
    sc.light += glow(cr, s, 1.2, 1.2) + heart * 0.9
    sc.light += np.exp(-(dcore / (R * 9)) ** 2) * 0.22          # ambient spill onto the plates
    sc.base += grain(sc, 0.006)
