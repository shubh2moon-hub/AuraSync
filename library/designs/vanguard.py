"""Angular armour panels with glowing seams and chevron accents - a gaming-hardware look, no logos."""
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Vanguard"
DESC = "Dark armour plating cut at one sharp angle, with glowing seams and chevrons."
COLOR = "#ff1e1e"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    ang = np.deg2rad(62)                         # every diagonal cut shares this angle
    dxdy = 1 / np.tan(ang)
    sc.base = vgrad(sc, (0.02, 0.02, 0.024), (0.007, 0.007, 0.009))

    # vertical-ish diagonal cuts at shared angle, uneven spacing
    xs = []
    x = -h * dxdy
    while x < w + sc.px(200):
        x += sc.px(sc.rng.choice([90, 160, 260, 420]))
        xs.append(x)
    # two stepped horizontal seams
    hy = [h * (0.34 if sc.landscape else 0.3), h * (0.68 if sc.landscape else 0.72)]

    face = np.zeros((h, w), np.float32)
    # panel index from position: which diagonal strip and which horizontal band
    u = sc.xx + (sc.yy - h) * dxdy
    strip = np.searchsorted(np.array(xs), u)
    band = (sc.yy > hy[0]).astype(int) + (sc.yy > hy[1]).astype(int)
    tone = np.mod((strip * 7 + band * 3) * 0.37, 1.0)
    # each panel: subtle gradient lit from the upper left
    grad = np.mod(u / sc.px(400), 1.0) * 0.3
    face = 0.018 + tone * 0.026 + grad * 0.01
    sc.base += (face + noise(sc, 0.7 * s, 0.0025))[..., None] * np.array([0.95, 1.0, 1.08])

    groove = np.zeros((h, w), np.float32)
    seam = np.zeros((h, w), np.float32)
    for x0 in xs:
        p, q = (x0, h + 5), (x0 - (h + 10) * dxdy, -5)
        lines(sc, [[p, q]], 6 * s, 1.0, groove)
        if sc.rng.random() < 0.45:                         # lit stretch with tapered ends
            t0 = sc.rng.uniform(0.0, 0.6); t1 = min(1, t0 + sc.rng.uniform(0.15, 0.45))
            n = 12
            for k in range(n):
                a = t0 + (t1 - t0) * k / n; b = t0 + (t1 - t0) * (k + 1) / n
                v = np.sin(np.pi * (k + 0.5) / n) ** 0.6
                lines(sc, [[(p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a),
                            (p[0] + (q[0] - p[0]) * b, p[1] + (q[1] - p[1]) * b)]], 2.4 * s, v, seam)
    for i, y in enumerate(hy):
        step = sc.px(30) * (1 if i == 0 else -1)
        xm = w * (0.42 if i == 0 else 0.58)
        path = [(-5, y), (xm, y), (xm + abs(step), y + step), (w + 5, y + step)]
        lines(sc, [path], 6 * s, 1.0, groove)
        lines(sc, [path], 2.6 * s, 0.9, seam)
    sc.base *= (1 - groove * 0.8)[..., None]

    # chevrons on the lower band, pointing along the seam
    chev = np.zeros((h, w), np.float32)
    cx, cy = (w * 0.16, hy[1] + sc.px(110)) if sc.landscape else (w * 0.3, hy[1] + sc.px(120))
    for i in range(5):
        L = sc.px(46); off = sc.px(30) * i
        lines(sc, [[(cx + off, cy - L), (cx + off + L * 0.7, cy), (cx + off, cy + L)]], 5 * s, 1.0 - i * 0.15, chev)
    # status ticks on the upper band
    ticks = np.zeros((h, w), np.float32)
    tx, ty = w * (0.62 if sc.landscape else 0.2), hy[0] - sc.px(36)
    for i in range(14):
        lines(sc, [[(tx + i * sc.px(20), ty), (tx + i * sc.px(20) + sc.px(10), ty)]], 3.5 * s, 0.85 if i % 4 else 0.35, ticks)

    lit = seam + chev + ticks
    sc.light += glow(lit, s, 1.0, 0.9) * 0.9
    sc.light += blur(seam, 50 * s) * 0.5 + blur(chev, 160 * s) * 1.2
    sc.base += grain(sc, 0.006)
