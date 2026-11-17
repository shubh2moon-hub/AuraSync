"""Tool to convert popular anime, movie, and live wallpapers into AuraSync live wallpaper packs."""
import os, sys, json
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit import PHONE, PHONE_LAND, PC, _jpg, blur, glow

HERE = os.path.dirname(os.path.abspath(__file__))
PACKS_DIR = os.path.join(HERE, "packs")


def crop_to_aspect(img, target_w, target_h, focal_x=0.5, focal_y=0.5):
    """Crops and resizes img to (target_w, target_h) around (focal_x, focal_y)."""
    src_h, src_w = img.shape[:2]
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h

    if src_aspect > target_aspect:
        # Source is wider than target: crop width
        new_w = int(src_h * target_aspect)
        new_h = src_h
        # Position crop window centered on focal_x
        center_x = int(src_w * focal_x)
        x0 = max(0, min(src_w - new_w, center_x - new_w // 2))
        y0 = 0
    else:
        # Source is taller than target: crop height
        new_w = src_w
        new_h = int(src_w / target_aspect)
        # Position crop window centered on focal_y
        center_y = int(src_h * focal_y)
        x0 = 0
        y0 = max(0, min(src_h - new_h, center_y - new_h // 2))

    cropped = img[y0:y0 + new_h, x0:x0 + new_w]
    return cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA if new_w > target_w else cv2.INTER_LANCZOS4)


def extract_light_map(img_rgb01, kind="general", custom_mask_fn=None):
    """Extracts the emissive glowing elements (swords, eyes, neon, comets) into a light layer."""
    h, w = img_rgb01.shape[:2]
    s = min(w, h) / 1080.0

    if custom_mask_fn is not None:
        core = custom_mask_fn(img_rgb01)
    elif kind == "lightsaber":
        # Intense white/colored blade core + bright colored glow
        gray = cv2.cvtColor((img_rgb01 * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        r, g, b = img_rgb01[..., 0], img_rgb01[..., 1], img_rgb01[..., 2]
        # Blade is either white-hot or strong red/blue
        is_red_blade = (r > 0.6) & (r > g * 1.4) & (r > b * 1.4)
        is_white_core = (gray > 0.88)
        core = np.clip(is_red_blade.astype(np.float32) * 1.2 + is_white_core.astype(np.float32) * 1.0, 0, 1)
    elif kind == "neon":
        # High saturation + high brightness
        hsv = cv2.cvtColor((img_rgb01 * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
        sat = hsv[..., 1] / 255.0
        val = hsv[..., 2] / 255.0
        core = np.clip((val - 0.5) * 2.0 * (sat * 0.7 + 0.3), 0, 1) ** 1.8
    elif kind == "cyberpunk":
        # Highlights: bright cyan, yellow, pink, and white
        gray = cv2.cvtColor((img_rgb01 * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        core = np.clip((gray - 0.65) / 0.35, 0, 1) ** 1.6
    else:
        gray = cv2.cvtColor((img_rgb01 * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        core = np.clip((gray - 0.72) / 0.28, 0, 1) ** 2.0

    # Build multi-tier glow from core
    light_map = (
        core * 0.95 +
        blur(core, 2.5 * s) * 0.8 +
        blur(core, 9.0 * s) * 0.5 +
        blur(core, 28.0 * s) * 0.28 +
        blur(core, 70.0 * s) * 0.14
    )
    light_map = np.clip(light_map, 0, 1)

    # Subdue the emissive core in base so it doesn't get double-blown out
    base = img_rgb01 * (1.0 - np.clip(core, 0, 1)[..., None] * 0.45)
    return base, light_map


def build_pack_from_images(pack_id, name, desc, default_color,
                           src_landscape_path, src_portrait_path=None,
                           land_focal=(0.5, 0.5), port_focal=(0.5, 0.5),
                           kind="general", custom_mask_fn=None):
    """Generates a complete AuraSync pack."""
    out_dir = os.path.join(PACKS_DIR, pack_id)
    os.makedirs(out_dir, exist_ok=True)
    col = np.array([int(default_color[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255

    img_land_src = cv2.cvtColor(cv2.imread(src_landscape_path), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    if src_portrait_path and os.path.exists(src_portrait_path):
        img_port_src = cv2.cvtColor(cv2.imread(src_portrait_path), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    else:
        img_port_src = img_land_src

    # 1. Native Phone Portrait (1080 x 2408)
    pw, ph = PHONE
    cropped_port = crop_to_aspect(img_port_src, pw, ph, port_focal[0], port_focal[1])
    port_base, port_light = extract_light_map(cropped_port, kind, custom_mask_fn)
    _jpg(os.path.join(out_dir, "phone_base.jpg"), port_base)
    _jpg(os.path.join(out_dir, "phone_light.jpg"), gray01=port_light)

    # Small preview
    prev_p_size = (360, round(ph * 360 / pw))
    pb_prev = cv2.resize(port_base, prev_p_size, interpolation=cv2.INTER_AREA)
    pl_prev = cv2.resize(port_light, prev_p_size, interpolation=cv2.INTER_AREA)
    # Composite preview with default color
    comp_p = np.clip(pb_prev + pl_prev[..., None] * col + (pl_prev[..., None] ** 2) * 0.4, 0, 1)
    _jpg(os.path.join(out_dir, "phone_preview.jpg"), comp_p, q=88)

    # 2. Native Phone Landscape (2408 x 1080)
    lw, lh = PHONE_LAND
    cropped_land = crop_to_aspect(img_land_src, lw, lh, land_focal[0], land_focal[1])
    land_base, land_light = extract_light_map(cropped_land, kind, custom_mask_fn)
    _jpg(os.path.join(out_dir, "phone_land_base.jpg"), land_base)
    _jpg(os.path.join(out_dir, "phone_land_light.jpg"), gray01=land_light)

    prev_l_size = (round(lw * 200 / lh), 200)
    lb_prev = cv2.resize(land_base, prev_l_size, interpolation=cv2.INTER_AREA)
    ll_prev = cv2.resize(land_light, prev_l_size, interpolation=cv2.INTER_AREA)
    comp_l = np.clip(lb_prev + ll_prev[..., None] * col + (ll_prev[..., None] ** 2) * 0.4, 0, 1)
    _jpg(os.path.join(out_dir, "phone_land_preview.jpg"), comp_l, q=88)

    # 3. PC Desktop (3840 x 2160)
    pcw, pch = PC
    cropped_pc = crop_to_aspect(img_land_src, pcw, pch, land_focal[0], land_focal[1])
    pc_base, pc_light = extract_light_map(cropped_pc, kind, custom_mask_fn)
    _jpg(os.path.join(out_dir, "pc_base.jpg"), pc_base)
    _jpg(os.path.join(out_dir, "pc_light.jpg"), gray01=pc_light)

    pc_prev_size = (960, 540)
    pcb_prev = cv2.resize(pc_base, pc_prev_size, interpolation=cv2.INTER_AREA)
    pcl_prev = cv2.resize(pc_light, pc_prev_size, interpolation=cv2.INTER_AREA)
    comp_pc = np.clip(pcb_prev + pcl_prev[..., None] * col + (pcl_prev[..., None] ** 2) * 0.4, 0, 1)
    _jpg(os.path.join(out_dir, "pc_preview.jpg"), comp_pc, q=88)

    # Legacy master files
    _jpg(os.path.join(out_dir, "master_base.jpg"), pc_base)
    _jpg(os.path.join(out_dir, "master_light.jpg"), gray01=pc_light)
    _jpg(os.path.join(out_dir, "master_base_small.jpg"), cv2.resize(pc_base, (1284, round(pch * 1284 / pcw)), interpolation=cv2.INTER_AREA), q=90)
    _jpg(os.path.join(out_dir, "master_light_small.jpg"), gray01=cv2.resize(pc_light, (1284, round(pch * 1284 / pcw)), interpolation=cv2.INTER_AREA), q=90)

    # 4. Meta JSON
    meta = {
        "id": pack_id,
        "name": name,
        "description": desc,
        "credits": "Wallpaper Engine / Community Artwork",
        "license": "Fair use / Personal wallpaper synchronization",
        "default_color": default_color,
        "phone": {
            "mode": "native",
            "x0": 0.0,
            "x1": 1.0,
            "land_x0": 0.0,
            "land_x1": 1.0
        }
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)

    print(f"Pack created: {pack_id} ({name})")
    return out_dir
