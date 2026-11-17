"""Turns whatever wallpaper the PC is showing into phone assets.

Lights are found two ways:
  * glow detection on the still image: small, saturated, locally bright spots of any color
  * learned from the live wallpaper: pixels whose color shifts while an Aura effect animates
The phone crop is placed where the lights are, then the lights are neutralized in the
background image so the phone can paint them in any color.
"""
import hashlib, io, json, winreg, zipfile
import numpy as np
from PIL import Image, ImageFilter

PHONE_W, PHONE_H = 1080, 2408


def current_wallpaper():
    """Path Windows (and Armoury Crate) currently uses as the desktop image."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
        return winreg.QueryValueEx(k, "WallPaper")[0]


def glow_mask(rgb):
    """0..1: saturated spots that are clearly brighter than their surroundings."""
    f = rgb.astype(np.float32) / 255.0
    v = f.max(axis=2)
    s = (v - f.min(axis=2)) / np.maximum(v, 1e-3)
    v_img = Image.fromarray((v * 255).astype(np.uint8))
    local = np.asarray(v_img.filter(ImageFilter.GaussianBlur(radius=max(4, rgb.shape[1] // 300)))) / 255.0
    lift = np.clip((v - local - 0.02) / 0.12, 0, 1)
    sat = np.clip((s - 0.35) / 0.3, 0, 1)
    bright = np.clip((v - 0.3) / 0.3, 0, 1)
    m = sat * bright * np.maximum(lift, 0.35 * sat * bright)
    return np.where(m < 0.18, 0, m)  # drop faint haze and edge noise


def build(image_path, learned_mask=None):
    """Returns (zip_bytes, sha_hash, pc_mask_image) for the wallpaper at image_path.

    learned_mask: optional 0..1 float array (any size) of pixels seen changing with Aura.
    pc_mask_image: L-mode image at source resolution, used by the PC to sample light colors.
    """
    src = Image.open(image_path).convert("RGB")
    W, H = src.size
    rgb = np.asarray(src)

    mask = glow_mask(rgb)
    if learned_mask is not None:
        lm = np.asarray(Image.fromarray((learned_mask * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)) / 255.0
        # where the live wallpaper proved which pixels are lights, trust that over the guess
        mask = np.maximum(lm, mask * 0.25) if lm.mean() > 0.0005 else mask
    mask_img = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8))
    pc_mask = mask_img.filter(ImageFilter.MaxFilter(5))

    # Pick the phone crop: the 20:9 window with the most light, gently pulled toward the center.
    crop_w = min(W, round(H * PHONE_W / PHONE_H))
    col = mask.sum(axis=0)
    csum = np.concatenate([[0], np.cumsum(col)])
    best_x, best = 0, -1.0
    for x in range(0, W - crop_w + 1, max(1, W // 240)):
        center_pull = 1 - 0.35 * abs((x + crop_w / 2) / W - 0.5) * 2
        score = (csum[x + crop_w] - csum[x] + col.sum() * 0.02) * center_pull
        if score > best:
            best_x, best = x, score

    phone = np.asarray(src.crop((best_x, 0, best_x + crop_w, H)).resize((PHONE_W, PHONE_H), Image.LANCZOS)).astype(np.float32)
    m_crop = mask_img.crop((best_x, 0, best_x + crop_w, H)).resize((PHONE_W, PHONE_H), Image.BILINEAR)
    m = np.asarray(m_crop.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.2))).astype(np.float32) / 255.0
    lum = phone.max(axis=2) / 255.0

    # Phone draws: background * (1 - m) + color * light. Lit areas keep their shading (lum) and
    # take the Aura color; small bright lights also get a soft bloom.
    bg = phone * (1 - m[..., None] * 0.85)
    core = np.clip(m * (0.15 + 0.95 * lum), 0, 1)
    core_img = Image.fromarray((core * 255).astype(np.uint8))
    blur = lambda r: np.asarray(core_img.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0
    spots = np.clip(core - blur(12), 0, 1)       # small, bright lights stand out from their blur
    spots_img = Image.fromarray((spots * 255).astype(np.uint8))
    sblur = lambda r: np.asarray(spots_img.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0
    light = np.clip(core * 1.05 + sblur(4) * 1.6 + sblur(14) * 1.4 + sblur(40) * 0.8, 0, 1)

    meta = {"src_w": W, "src_h": H, "crop_x": best_x, "crop_w": crop_w,
            "phone_w": PHONE_W, "phone_h": PHONE_H, "grid_w": 16, "grid_h": 9}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        b = io.BytesIO()
        Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).save(b, "JPEG", quality=88)
        z.writestr("bg.jpg", b.getvalue())
        b = io.BytesIO()
        Image.fromarray((light * 255).astype(np.uint8), "L").save(b, "JPEG", quality=90)
        z.writestr("mask.jpg", b.getvalue())
        z.writestr("meta.json", json.dumps(meta))
    blob = buf.getvalue()
    return blob, hashlib.sha1(blob).hexdigest()[:16], pc_mask


if __name__ == "__main__":
    blob, h, pm = build(current_wallpaper())
    open("preview_assets.zip", "wb").write(blob)
    print("hash", h, "size", len(blob))
