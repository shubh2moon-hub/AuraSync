"""Cyberpunk skyline: layered towers in fog, neon edges and signs, wet street reflections."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Night District"
DESC = "Foggy neon skyline with lit tower edges, signs and a rain-soaked street."
COLOR = "#ff3b5c"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    street = h * (0.80 if sc.landscape else 0.82)
    sc.base = vgrad(sc, (0.012, 0.014, 0.03), (0.05, 0.035, 0.07), 1.3)

    neon = np.zeros((h, w), np.float32)
    layers = [  # (count, min height, max height, fog, darkness)
        (34 if sc.landscape else 12, 0.20, 0.45, 0.55, 0.075),
        (22 if sc.landscape else 9, 0.30, 0.62, 0.30, 0.045),
        (13 if sc.landscape else 6, 0.40, 0.78, 0.0, 0.022),
    ]
    tall = 1.0 if sc.landscape else 1.3
    # city glow in the sky behind the towers, tinted by the Aura color
    haze = np.exp(-((sc.yy - street * 0.72) / (0.32 * h)) ** 2) * (sc.yy < street)
    sc.light += haze * 0.42
    sc.base += haze[..., None] * np.array([0.03, 0.025, 0.05])
    for li, (count, hmin, hmax, fog, dark) in enumerate(layers):
        hmin, hmax = hmin * tall, min(hmax * tall, 0.92)
        x = -sc.px(40)
        layer_mask = np.zeros((h, w), np.float32)
        layer_neon = np.zeros((h, w), np.float32)
        windows = np.zeros((h, w), np.float32)
        while x < w:
            bw = w / count * sc.rng.uniform(0.6, 1.5)
            top = street - sc.rng.uniform(hmin, hmax) * street
            rect = [(x, top), (x + bw, top), (x + bw, street), (x, street)]
            # occasional stepped crown
            if sc.rng.random() < 0.4:
                inset = bw * sc.rng.uniform(0.15, 0.3)
                ctop = top - sc.rng.uniform(0.03, 0.08) * street
                polys(sc, [[(x + inset, ctop), (x + bw - inset, ctop), (x + bw - inset, top + 1), (x + inset, top + 1)]], 1.0, layer_mask)
                if sc.rng.random() < 0.7:
                    lines(sc, [[(x + inset, ctop), (x + bw - inset, ctop)]], 2.5 * s, 1.0, layer_neon)
                if sc.rng.random() < 0.5:   # antenna with beacon
                    ax = x + bw / 2
                    lines(sc, [[(ax, ctop), (ax, ctop - sc.px(60))]], 1.5 * s, 1.0, windows)
                    polys(sc, [[(ax + sc.px(4) * np.cos(a), ctop - sc.px(60) + sc.px(4) * np.sin(a)) for a in np.linspace(0, 6.3, 12)]], 1.0, layer_neon)
            polys(sc, [rect], 1.0, layer_mask)
            r = sc.rng.random()
            if r < 0.45:     # vertical neon strip on an edge
                ex = x + (bw * 0.08 if sc.rng.random() < 0.5 else bw * 0.92)
                lines(sc, [[(ex, top + sc.px(10)), (ex, street - sc.px(sc.rng.uniform(40, 200)))]], 3 * s, 1.0, layer_neon)
            elif r < 0.7:    # rooftop bar
                lines(sc, [[(x + bw * 0.1, top + sc.px(8)), (x + bw * 0.9, top + sc.px(8))]], 3 * s, 1.0, layer_neon)
            if li == 2 and sc.rng.random() < 0.5:   # front sign: outlined box with inner bars
                sw = min(bw * 0.7, sc.px(160)); sh = sw * sc.rng.uniform(0.35, 1.6)
                sx = x + (bw - sw) / 2; sy = top + (street - top) * sc.rng.uniform(0.15, 0.5)
                box = [(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh), (sx, sy)]
                lines(sc, [box], 3 * s, 1.0, layer_neon)
                for k in range(int(sc.rng.integers(1, 4))):
                    yy = sy + sh * (k + 1) / 4
                    lines(sc, [[(sx + sw * 0.18, yy), (sx + sw * sc.rng.uniform(0.45, 0.82), yy)]], 2.5 * s, 0.8, layer_neon)
            # warm windows (not Aura lights, they stay as they are)
            cols = max(2, int(bw / sc.px(22)))
            rows = int((street - top) / sc.px(26))
            lit = sc.rng.random((rows, cols)) < 0.12
            for ri, ci in zip(*np.nonzero(lit)):
                wx = x + (ci + 0.3) * bw / cols
                wy = top + sc.px(20) + ri * sc.px(26)
                polys(sc, [[(wx, wy), (wx + sc.px(8), wy), (wx + sc.px(8), wy + sc.px(12)), (wx, wy + sc.px(12))]],
                      sc.rng.uniform(0.3, 1.0), windows)
            x += bw + sc.px(sc.rng.uniform(0, 14))
        shade = vgrad(sc, (dark, dark * 1.05, dark * 1.7), (dark * 0.6, dark * 0.6, dark))
        fogc = np.array([0.09, 0.07, 0.13])
        body = shade * (1 - fog) + fogc * fog
        sc.base = sc.base * (1 - layer_mask[..., None]) + body * layer_mask[..., None]
        sc.base += windows[..., None] * np.array([1.0, 0.72, 0.4]) * (0.35 * (1 - fog) + 0.08) * layer_mask[..., None]
        sc.light *= 1 - layer_mask * (1 - fog * 0.75)   # far towers are hazy, haze shows through
        neon *= 1 - layer_mask
        neon += layer_neon * (1 - fog * 0.6)

    # fog band low in the city
    fogband = np.exp(-((sc.yy - street * 0.9) / (0.18 * h)) ** 2) * 0.6
    sc.base += fogband[..., None] * np.array([0.05, 0.035, 0.07])

    lit = glow(neon, s, 1.0, 0.8)
    sc.light += lit * 0.85 + blur(neon, 140 * s) * 0.35 * (sc.yy < street)

    # street: dark wet asphalt with stretched reflections
    below = sc.yy >= street
    sc.base[below] = (vgrad(sc, (0.03, 0.025, 0.04), (0.008, 0.008, 0.012))[below])
    rows = np.arange(h)
    src = (2 * street - rows).astype(int)
    ok = (rows >= street) & (src >= 0)
    refl = np.zeros_like(sc.light)
    refl[ok] = sc.light[src[ok]]
    refl = blur(refl, 2 * s)
    # vertical smear like rain-soaked ground
    import cv2
    refl = cv2.GaussianBlur(refl, (0, 0), sigmaX=2 * s, sigmaY=14 * s)
    ripple = 0.65 + 0.35 * np.sin(sc.yy / sc.px(5) + noise(sc, 3 * s, 2.0))
    sc.light += refl * ripple * 0.85 * np.clip(1 - (sc.yy - street) / (h - street + 1) * 0.7, 0, 1)
    lines(sc, [[(0, street), (w, street)]], 1.5 * s, 0.25, sc.light)
    sc.base += grain(sc, 0.008)
