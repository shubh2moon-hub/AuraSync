"""Makes a pack's phone wallpaper from its master scene.

Two framings (stored in meta.json under "phone"):
  crop   - a 1080x2408 portrait window of the scene; "center" is its horizontal center (0..1)
  whole  - the entire scene across the phone's width, with a soft blurred copy filling above and below;
           "offset" (0..1) places the picture vertically
The effect engine maps phone pixels back to scene x using phone.x0..x1, so effects line up with the PC.
"""
import json, os, sys
import cv2
import numpy as np
from toolkit import PHONE, composite, _jpg, blur


def load(pack_dir, name):
    if name.endswith("base"):
        return cv2.cvtColor(cv2.imread(os.path.join(pack_dir, "master_base.jpg")), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    return cv2.imread(os.path.join(pack_dir, "master_light.jpg"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255


def make_phone(pack_dir, mode=None, center=None, offset=None):
    meta_path = os.path.join(pack_dir, "meta.json")
    meta = json.load(open(meta_path))
    ph = dict(meta.get("phone") or {})
    if mode is None and ph.get("mode") == "native":
        return meta
    if mode: ph["mode"] = mode
    if center is not None: ph["center"] = float(min(max(center, 0), 1))
    if offset is not None: ph["offset"] = float(min(max(offset, 0), 1))
    ph.setdefault("mode", "crop"); ph.setdefault("center", 0.5); ph.setdefault("offset", 0.5)

    base = load(pack_dir, "base")
    light = load(pack_dir, "light")
    H, W = light.shape
    pw, phh = PHONE

    if ph["mode"] == "crop":
        cw = round(H * pw / phh)
        x = int(round(ph["center"] * W - cw / 2))
        x = min(max(x, 0), W - cw)
        b = cv2.resize(base[:, x:x + cw], (pw, phh), interpolation=cv2.INTER_AREA)
        l = cv2.resize(light[:, x:x + cw], (pw, phh), interpolation=cv2.INTER_AREA)
        ph["center"] = round((x + cw / 2) / W, 4)
        ph["x0"], ph["x1"] = round(x / W, 4), round((x + cw) / W, 4)
    else:
        fh = round(H * pw / W)                              # picture height at phone width
        top = int(round((phh - fh) * ph["offset"]))
        pic_b = cv2.resize(base, (pw, fh), interpolation=cv2.INTER_AREA)
        pic_l = cv2.resize(light, (pw, fh), interpolation=cv2.INTER_AREA)
        # fill: the scene scaled to cover the screen, blurred and dimmed
        cw = round(H * pw / phh)
        x = (W - cw) // 2
        fill_b = blur(cv2.resize(base[:, x:x + cw], (pw, phh), interpolation=cv2.INTER_AREA), 40) * 0.45
        fill_l = blur(cv2.resize(light[:, x:x + cw], (pw, phh), interpolation=cv2.INTER_AREA), 40) * 0.5
        # feathered seam between picture and fill
        yy = np.arange(phh, dtype=np.float32)
        feather = 24.0
        a = np.clip(np.minimum(yy - top, top + fh - yy) / feather, 0, 1)[:, None]
        b = fill_b.copy(); l = fill_l.copy()
        b[top:top + fh] = pic_b; l[top:top + fh] = pic_l
        b = fill_b * (1 - a[..., None]) + b * a[..., None]
        l = fill_l * (1 - a) + l * a
        ph["x0"], ph["x1"] = 0.0, 1.0

    _jpg(os.path.join(pack_dir, "phone_base.jpg"), b)
    _jpg(os.path.join(pack_dir, "phone_light.jpg"), gray01=l)
    col = np.array([int(meta["default_color"][i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
    small = (360, round(phh * 360 / pw))
    _jpg(os.path.join(pack_dir, "phone_preview.jpg"),
         composite(cv2.resize(b, small, interpolation=cv2.INTER_AREA), cv2.resize(l, small, interpolation=cv2.INTER_AREA), col), q=88)
    meta["phone"] = ph
    json.dump(meta, open(meta_path, "w"), indent=1)
    return meta


if __name__ == "__main__":
    # python phone.py <pack_dir> [crop <center> | whole <offset>]
    d = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "whole":
        print(make_phone(d, "whole", offset=float(sys.argv[3]) if len(sys.argv) > 3 else None)["phone"])
    elif len(sys.argv) > 2:
        print(make_phone(d, "crop", center=float(sys.argv[3]) if len(sys.argv) > 3 else None)["phone"])
    else:
        print(make_phone(d)["phone"])
