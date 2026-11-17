"""Drawing helpers for AuraSync wallpaper packs.

A wallpaper is two layers per orientation:
  base  - the scene with every Aura light switched off (RGB, 0..1)
  light - where Aura color is added and how strongly (0..1); includes glow and reflections
Displayed pixel = base + light * effect_color, with a white-hot core where light is strongest.
"""
import json, os
import cv2
import numpy as np

PC = (3840, 2160)
PHONE = (1080, 2408)
PHONE_LAND = (2408, 1080)


class Scene:
    def __init__(self, w, h, seed=0):
        self.w, self.h = w, h
        self.s = min(w, h) / 1080.0            # scale: 1.0 at 1080 px short side
        self.base = np.zeros((h, w, 3), np.float32)
        self.light = np.zeros((h, w), np.float32)
        self.rng = np.random.default_rng(seed)
        self.yy, self.xx = np.mgrid[0:h, 0:w].astype(np.float32)

    # ---- coordinates
    @property
    def landscape(self):
        return self.w > self.h

    def px(self, v):
        """Design units (1080-short-side) -> pixels."""
        return v * self.s


def blur(a, sigma):
    if sigma <= 0:
        return a.copy()
    if sigma > 24:   # big glows: blur a smaller copy, much faster and visually identical
        k = sigma / 12.0
        small = cv2.resize(a, (max(1, int(a.shape[1] / k)), max(1, int(a.shape[0] / k))), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), 12)
        return cv2.resize(small, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(a, (0, 0), sigma)


def glow(core, s=1.0, tight=1.0, wide=1.0):
    """Neon look: sharp core plus layered halos."""
    return (core * 1.0
            + blur(core, 2.5 * s) * 0.9 * tight
            + blur(core, 9 * s) * 0.55 * tight
            + blur(core, 30 * s) * 0.32 * wide
            + blur(core, 90 * s) * 0.18 * wide)


def lines(sc, segments, width, value=1.0, layer=None):
    """Antialiased polylines on a float layer. segments: list of [(x,y),...] in pixels."""
    tgt = np.zeros((sc.h, sc.w), np.float32) if layer is None else layer
    SH = 4
    for pts in segments:
        p = (np.asarray(pts, np.float64) * (1 << SH)).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(tgt, [p], False, float(value), max(1, int(round(width))), cv2.LINE_AA, SH)
    return tgt


def polys(sc, polygons, value=1.0, layer=None):
    tgt = np.zeros((sc.h, sc.w), np.float32) if layer is None else layer
    SH = 4
    for pts in polygons:
        p = (np.asarray(pts, np.float64) * (1 << SH)).astype(np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(tgt, [p], float(value), cv2.LINE_AA, SH)
    return tgt


def vgrad(sc, top, bottom, curve=1.0):
    t = (sc.yy / (sc.h - 1)) ** curve
    top, bottom = np.array(top, np.float32), np.array(bottom, np.float32)
    return top * (1 - t[..., None]) + bottom * t[..., None]


def noise(sc, sigma, amount):
    n = sc.rng.standard_normal((sc.h, sc.w)).astype(np.float32)
    n = blur(n, sigma)
    return n / (n.std() + 1e-6) * amount


def grain(sc, amount=0.012):
    return sc.rng.standard_normal((sc.h, sc.w, 1)).astype(np.float32) * amount


def mix(a, b, t):
    return a * (1 - t) + b * t


MASTER = (4282, 2408)   # one scene per wallpaper: PC = whole scene, phone = a 1080x2408 window or the whole scene


def _jpg(path, rgb01=None, gray01=None, q=92):
    if rgb01 is not None:
        cv2.imwrite(path, cv2.cvtColor((np.clip(rgb01, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, q])
    else:
        cv2.imwrite(path, (np.clip(gray01, 0, 1) * 255 + 0.5).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, q])


def save_pack(out_dir, name, desc, credits, sc_port, sc_land, default_color="#ff2a3a"):
    """Writes phone-first assets (native portrait and native landscape) plus PC assets."""
    os.makedirs(out_dir, exist_ok=True)
    col = np.array([int(default_color[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255

    # 1. Native Phone Portrait
    pb_base, pb_light = np.clip(sc_port.base, 0, 1), np.clip(sc_port.light, 0, 1)
    _jpg(os.path.join(out_dir, "phone_base.jpg"), pb_base)
    _jpg(os.path.join(out_dir, "phone_light.jpg"), gray01=pb_light)
    small_p = (360, round(sc_port.h * 360 / sc_port.w))
    _jpg(os.path.join(out_dir, "phone_preview.jpg"),
         composite(cv2.resize(pb_base, small_p, interpolation=cv2.INTER_AREA),
                   cv2.resize(pb_light, small_p, interpolation=cv2.INTER_AREA), col), q=88)

    # 2. Native Phone Landscape
    pl_base, pl_light = np.clip(sc_land.base, 0, 1), np.clip(sc_land.light, 0, 1)
    _jpg(os.path.join(out_dir, "phone_land_base.jpg"), pl_base)
    _jpg(os.path.join(out_dir, "phone_land_light.jpg"), gray01=pl_light)
    small_l = (round(sc_land.w * 200 / sc_land.h), 200)
    _jpg(os.path.join(out_dir, "phone_land_preview.jpg"),
         composite(cv2.resize(pl_base, small_l, interpolation=cv2.INTER_AREA),
                   cv2.resize(pl_light, small_l, interpolation=cv2.INTER_AREA), col), q=88)

    # 3. PC Assets (3840 x 2160)
    pw, ph = PC
    pc_b = cv2.resize(pl_base, (pw, ph), interpolation=cv2.INTER_AREA if pl_base.shape[1] >= pw else cv2.INTER_CUBIC)
    pc_l = cv2.resize(pl_light, (pw, ph), interpolation=cv2.INTER_AREA if pl_light.shape[1] >= pw else cv2.INTER_CUBIC)
    _jpg(os.path.join(out_dir, "pc_base.jpg"), pc_b)
    _jpg(os.path.join(out_dir, "pc_light.jpg"), gray01=pc_l)
    _jpg(os.path.join(out_dir, "pc_preview.jpg"),
         composite(cv2.resize(pc_b, (960, 540), interpolation=cv2.INTER_AREA),
                   cv2.resize(pc_l, (960, 540), interpolation=cv2.INTER_AREA), col), q=88)

    # 4. Master for backwards compatibility
    _jpg(os.path.join(out_dir, "master_base.jpg"), pc_b)
    _jpg(os.path.join(out_dir, "master_light.jpg"), gray01=pc_l)
    sw = 1284
    shh = round(ph * sw / pw)
    _jpg(os.path.join(out_dir, "master_base_small.jpg"), cv2.resize(pc_b, (sw, shh), interpolation=cv2.INTER_AREA), q=90)
    _jpg(os.path.join(out_dir, "master_light_small.jpg"), gray01=cv2.resize(pc_l, (sw, shh), interpolation=cv2.INTER_AREA), q=90)

    # 5. Metadata
    meta_path = os.path.join(out_dir, "meta.json")
    meta = {
        "id": os.path.basename(out_dir),
        "name": name,
        "description": desc,
        "credits": credits,
        "license": "Original artwork, generated for AuraSync",
        "default_color": default_color,
        "phone": {
            "mode": "native",
            "x0": 0.0,
            "x1": 1.0,
            "land_x0": 0.0,
            "land_x1": 1.0
        },
        "pc": {
            "w": pw,
            "h": ph
        }
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=1)
    return meta


def save_master(out_dir, name, desc, credits, sc, default_color="#ff2a3a"):
    """Writes the master scene, the PC version and small copies for the gallery."""
    os.makedirs(out_dir, exist_ok=True)
    base, light = np.clip(sc.base, 0, 1), np.clip(sc.light, 0, 1)
    _jpg(os.path.join(out_dir, "master_base.jpg"), base)
    _jpg(os.path.join(out_dir, "master_light.jpg"), gray01=light)
    pw, ph = PC
    pb = cv2.resize(base, (pw, ph), interpolation=cv2.INTER_AREA)
    pl = cv2.resize(light, (pw, ph), interpolation=cv2.INTER_AREA)
    _jpg(os.path.join(out_dir, "pc_base.jpg"), pb)
    _jpg(os.path.join(out_dir, "pc_light.jpg"), gray01=pl)
    sw = 1284
    shh = round(sc.h * sw / sc.w)
    _jpg(os.path.join(out_dir, "master_base_small.jpg"), cv2.resize(base, (sw, shh), interpolation=cv2.INTER_AREA), q=90)
    _jpg(os.path.join(out_dir, "master_light_small.jpg"), gray01=cv2.resize(light, (sw, shh), interpolation=cv2.INTER_AREA), q=90)
    col = np.array([int(default_color[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    _jpg(os.path.join(out_dir, "pc_preview.jpg"), composite(cv2.resize(pb, (960, 540), interpolation=cv2.INTER_AREA),
                                                           cv2.resize(pl, (960, 540), interpolation=cv2.INTER_AREA), col), q=88)
    meta_path = os.path.join(out_dir, "meta.json")
    old = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    meta = {"id": os.path.basename(out_dir), "name": name, "description": desc, "credits": credits,
            "license": "Original artwork, generated for AuraSync", "default_color": default_color,
            "master": {"w": sc.w, "h": sc.h}, "pc": {"w": pw, "h": ph},
            "phone": old.get("phone") or {"mode": "crop", "center": best_center(light)}}
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=1)
    return meta


def best_center(light):
    """Horizontal center (0..1) of the portrait window holding the most light, pulled gently to the middle."""
    h, w = light.shape
    cw = round(h * PHONE[0] / PHONE[1])
    col = light.sum(axis=0)
    cs = np.concatenate([[0], np.cumsum(col)])
    best, bx = -1, (w - cw) // 2
    for x in range(0, w - cw + 1, max(1, w // 200)):
        c = (x + cw / 2) / w
        score = (cs[x + cw] - cs[x]) * (1 - 0.6 * abs(c - 0.5))
        if score > best:
            best, bx = score, x
    return round((bx + cw / 2) / w, 4)


def composite(base, light, color):
    """Same formula the PC and phone renderers use."""
    hot = np.clip((light - 0.88) / 0.12, 0, 1)[..., None] * 0.35
    out = base * (1 - 0.55 * light[..., None]) + light[..., None] * color[None, None, :] * 0.95
    out = np.minimum(out, 1)
    return np.clip(out + hot * (1 - out), 0, 1)
