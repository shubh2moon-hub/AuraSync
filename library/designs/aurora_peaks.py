"""Night mountains under an aurora, mirrored in a still lake."""
import cv2
import numpy as np
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Aurora Peaks"
DESC = "Aurora curtains over snowy peaks, reflected in a mirror-still lake."
COLOR = "#2bff88"


def ridge(sc, base_y, amp, rough, peaks):
    """Jagged mountain line by midpoint displacement, scaled to amp pixels tall."""
    n = 2 ** 10 + 1
    y = np.zeros(n)
    y[0], y[-1] = sc.rng.uniform(0.1, 0.4), sc.rng.uniform(0.1, 0.4)
    step, scale = n - 1, 1.0
    while step > 1:
        half = step // 2
        for i in range(half, n - 1, step):
            y[i] = (y[i - half] + y[i + half]) / 2 + sc.rng.uniform(-1, 1) * scale
        step, scale = half, scale * rough
    xs = np.linspace(0, sc.w, n)
    # a few dominant peaks
    for _ in range(peaks):
        c = sc.rng.uniform(0.05, 0.95) * sc.w
        y += np.clip(1 - np.abs(xs - c) / (max(sc.w, sc.h * 0.7) * sc.rng.uniform(0.08, 0.2)), 0, 1) * sc.rng.uniform(0.8, 1.6)
    y = (y - y.min()) / (np.ptp(y) + 1e-6)
    return xs, base_y - y * amp


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    lake = h * (0.70 if sc.landscape else 0.72)
    sc.base = vgrad(sc, (0.004, 0.008, 0.02), (0.02, 0.035, 0.06), 1.4)

    # stars
    n = int(w * h / 6000)
    st = np.zeros((h, w), np.float32)
    xs, ys = sc.rng.uniform(0, w, n).astype(int), sc.rng.uniform(0, lake, n).astype(int)
    st[ys, xs] = sc.rng.uniform(0.1, 1.0, n) ** 3
    st = blur(st, 0.6 * s) * 4
    sc.base += st[..., None] * np.array([0.85, 0.9, 1.0])

    # aurora: vertical rays shaped by a wavy ribbon
    u = sc.xx / w
    band_y = h * (0.40 if sc.landscape else 0.44) + np.sin(u * 7.0 + 1.3) * h * 0.06 + np.sin(u * 17 + 0.4) * h * 0.02
    rays = cv2.resize(sc.rng.random((1, 900)).astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    rays = blur(rays, 1.5 * s)
    rays = (rays - rays.min()) / (np.ptp(rays) + 1e-6)
    above = np.clip((band_y - sc.yy) / (h * 0.33), 0, 1)       # rays rise above the ribbon
    below = np.clip(1 - (sc.yy - band_y) / (h * 0.07), 0, 1) ** 1.5  # soft lower edge
    curtain = np.where(sc.yy < band_y, (1 - above) ** 1.8, below) * (0.35 + 0.65 * rays ** 2)
    curtain *= 0.55 + 0.45 * np.sin(u * 3.1 + 2) ** 2
    second = np.roll(curtain, int(w * 0.23), axis=1) * 0.45
    second = np.roll(second, -int(h * 0.05), axis=0)
    aur = np.clip(curtain + second, 0, 1.2) * (sc.yy < lake)
    spill = blur(aur, 180 * s) * (sc.yy < lake)
    sc.light += aur * 0.75 + blur(aur, 50 * s) * 0.35 + spill * 0.9

    # mountains: back (hazy) and front (dark, snow highlights)
    for k, (amp, rough, tone) in enumerate([(0.36, 0.5, 0.05), (0.22, 0.55, 0.016)]):
        xs, ys = ridge(sc, lake + 2, amp * h * (1.0 if sc.landscape else 0.85), rough, 3 if sc.landscape else 2)
        pts = list(zip(xs, ys)) + [(w, lake + 2), (0, lake + 2)]
        m = polys(sc, [pts])
        col = vgrad(sc, (tone * 0.8, tone, tone * 1.6), (tone * 0.3, tone * 0.4, tone * 0.6))
        sc.base = sc.base * (1 - m[..., None]) + col * m[..., None]
        sc.light *= 1 - m * (0.85 if k else 0.6)
        rim = lines(sc, [list(zip(xs, ys))], 1.6 * s)
        sc.light += glow(rim, s, 0.6, 0.4) * (0.25 if k else 0.12)    # aurora light catching the ridges
        snow = m * np.clip(1 - (sc.yy - np.interp(sc.xx[0], xs, ys)[None, :]) / sc.px(60), 0, 1) * (0.06 if k else 0.03)
        sc.base += snow[..., None] * np.array([0.8, 0.85, 1.0])

    # lake reflection: mirror, ripple, darken
    rows = np.arange(h)
    src = np.clip((2 * lake - rows).astype(int), 0, h - 1)
    rip = (np.sin(sc.yy / sc.px(3.5)) * sc.px(2)).astype(np.float32)
    mapx = (sc.xx + rip).astype(np.float32)
    mapy = np.broadcast_to(src[:, None].astype(np.float32), (h, w)).copy()
    below_m = (sc.yy > lake)
    rb = cv2.remap(sc.base, mapx, mapy, cv2.INTER_LINEAR)
    rl = cv2.remap(sc.light, mapx, mapy, cv2.INTER_LINEAR)
    att = np.clip(1 - (sc.yy - lake) / (h - lake + 1), 0.25, 1)
    sc.base = np.where(below_m[..., None], rb * 0.55 * att[..., None] + np.array([0.004, 0.006, 0.01]), sc.base)
    sc.light = np.where(below_m, blur(rl, 1.5 * s) * 0.55 * att, sc.light)
    sc.light += lines(sc, [[(0, lake), (w, lake)]], 1.2 * s, 0.15)
    sc.base += grain(sc, 0.007)
