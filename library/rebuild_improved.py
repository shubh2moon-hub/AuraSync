"""
Improved Aura Mask Rebuild — v3
Key changes from v2:
- Every mask uses SMOOTH GRADIENT falloff (Gaussian blur from hero pixels), not binary on/off
- Ambient base layer: whole image gets tiny ambient so character body always has SOME glow
- Street lamps capped at 0.08 (not zero — zero looks harsh; 0.08 barely perceptible)
- Shoes/floor get max 0.06 ambient, never more
- Hero elements (blades, visor, comet core) get 0.80-0.90 peak, then gaussian falloff
- Result: cinematic rim-lighting, NOT uniform color overlay
"""
import os, sys, json, cv2, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == 'library' else HERE
sys.path.insert(0, HERE)
from toolkit import PHONE, PHONE_LAND, PC, _jpg, blur

PACKS_DIR = os.path.join(HERE, "packs")


def gblur(img, sigma_px):
    """Gaussian blur in pixels (not scale-relative)."""
    k = max(3, int(sigma_px * 3) | 1)
    return cv2.GaussianBlur(img, (k, k), sigma_px)


def make_gradient_mask(hero_binary, sigma_small, sigma_large, peak=0.85, falloff_weight=0.40):
    """
    Turn a binary hero mask into a smooth gradient via multi-scale gaussian blur.
    - sigma_small: tight glow halo around emissive core (pixels)
    - sigma_large: wide soft ambient spread
    - peak: max value at true hero pixels
    - falloff_weight: how much the blurred halo contributes
    """
    h = hero_binary.astype(np.float32)
    tight = gblur(h, sigma_small)
    wide  = gblur(h, sigma_large)
    result = h * peak + tight * falloff_weight * 0.6 + wide * falloff_weight * 0.3
    return np.clip(result, 0, 1)


def crop_to_aspect(img, target_w, target_h, focal_x=0.5, focal_y=0.5):
    src_h, src_w = img.shape[:2]
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h
    if src_aspect > target_aspect:
        new_w = int(src_h * target_aspect)
        new_h = src_h
        center_x = int(src_w * focal_x)
        x0 = max(0, min(src_w - new_w, center_x - new_w // 2))
        y0 = 0
    else:
        new_w = src_w
        new_h = int(src_w / target_aspect)
        center_y = int(src_h * focal_y)
        x0 = 0
        y0 = max(0, min(src_h - new_h, center_y - new_h // 2))
    cropped = img[y0:y0+new_h, x0:x0+new_w]
    return cv2.resize(cropped, (target_w, target_h),
                      interpolation=cv2.INTER_AREA if new_w > target_w else cv2.INTER_LANCZOS4)


def process_layer(img_rgb01, mask_fn):
    h, w = img_rgb01.shape[:2]
    s = min(w, h) / 1080.0
    core = mask_fn(img_rgb01, s)
    core = np.clip(core, 0, 1)

    # Multi-scale optical glow (tighter than before for less flooding)
    light_layer = (
        core         * 0.80 +
        blur(core, 2.5 * s) * 0.30 +
        blur(core, 7.0 * s) * 0.14 +
        blur(core, 20.0 * s) * 0.05
    )
    light_layer = np.clip(light_layer, 0, 1)
    # Darken base slightly where aura peaks
    base_layer = img_rgb01 * (1.0 - core[..., None] * 0.15)
    return base_layer, light_layer


def assemble_pack(pack_id, name, desc, default_color,
                  img_land_src, img_port_src=None,
                  land_focal=(0.5, 0.5), port_focal=(0.5, 0.5),
                  mask_fn=None):
    out_dir = os.path.join(PACKS_DIR, pack_id)
    os.makedirs(out_dir, exist_ok=True)
    col = np.array([int(default_color[i:i+2], 16) for i in (1, 3, 5)], np.float32) / 255

    if img_port_src is None:
        img_port_src = img_land_src

    def _build(img_rgb01, tw, th, fx, fy):
        cropped = crop_to_aspect(img_rgb01, tw, th, fx, fy)
        base, light = process_layer(cropped, mask_fn)
        return base, light, cropped

    # 1. Phone Portrait
    pw, ph = PHONE
    base_p, light_p, _ = _build(img_port_src, pw, ph, port_focal[0], port_focal[1])
    _jpg(os.path.join(out_dir, "phone_base.jpg"), base_p)
    _jpg(os.path.join(out_dir, "phone_light.jpg"), gray01=light_p)
    # preview
    prev_p_sz = (360, round(ph * 360 / pw))
    bp = cv2.resize(base_p, prev_p_sz, interpolation=cv2.INTER_AREA)
    lp = cv2.resize(light_p, prev_p_sz, interpolation=cv2.INTER_AREA)
    comp_p = np.clip(bp + lp[..., None] * col * 0.80 + (lp[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "phone_preview.jpg"), comp_p, q=88)

    # 2. Phone Landscape
    lw, lh = PHONE_LAND
    base_l, light_l, _ = _build(img_land_src, lw, lh, land_focal[0], land_focal[1])
    _jpg(os.path.join(out_dir, "phone_land_base.jpg"), base_l)
    _jpg(os.path.join(out_dir, "phone_land_light.jpg"), gray01=light_l)
    prev_l_sz = (round(lw * 200 / lh), 200)
    bl = cv2.resize(base_l, prev_l_sz, interpolation=cv2.INTER_AREA)
    ll = cv2.resize(light_l, prev_l_sz, interpolation=cv2.INTER_AREA)
    comp_l = np.clip(bl + ll[..., None] * col * 0.80 + (ll[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "phone_land_preview.jpg"), comp_l, q=88)

    # 3. PC 4K
    pcw, pch = PC
    base_pc, light_pc, _ = _build(img_land_src, pcw, pch, land_focal[0], land_focal[1])
    _jpg(os.path.join(out_dir, "pc_base.jpg"), base_pc)
    _jpg(os.path.join(out_dir, "pc_light.jpg"), gray01=light_pc)
    pc_prev = (960, 540)
    bpc = cv2.resize(base_pc, pc_prev, interpolation=cv2.INTER_AREA)
    lpc = cv2.resize(light_pc, pc_prev, interpolation=cv2.INTER_AREA)
    comp_pc = np.clip(bpc + lpc[..., None] * col * 0.80 + (lpc[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "pc_preview.jpg"), comp_pc, q=88)
    # legacy names
    _jpg(os.path.join(out_dir, "master_base.jpg"), base_pc)
    _jpg(os.path.join(out_dir, "master_light.jpg"), gray01=light_pc)

    meta = {
        "id": pack_id, "name": name, "description": desc,
        "credits": "Anime & Movie Live Wallpaper Edition",
        "license": "Personal live wallpaper synchronization",
        "default_color": default_color,
        "phone": {"mode": "native", "x0": 0.0, "x1": 1.0, "land_x0": 0.0, "land_x1": 1.0}
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(f"-> Pack done: {pack_id}")


# ─────────────────────────── MASK FUNCTIONS v3 ──────────────────────────────

def mask_demon_slayer(img, s):
    """
    Tanjiro: Smooth gradient aura.
    - Full body gets soft ambient base so character isn't dark
    - Visor + earring = hero peak (0.85)
    - Green katana + sheath = mid-hero (0.65)
    - Street lamps = capped at 0.06 (barely visible, not zero)
    - Shoes/floor = max 0.05
    - Everything uses gaussian falloff, NO hard binary cuts
    """
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    yy = np.arange(h)[:, None] / float(h)
    xx = np.arange(w)[None, :] / float(w)
    px = min(h, w)  # reference pixels for blur sigmas

    # ── 1. AMBIENT: soft base over CHARACTER BODY ONLY (not background, not floor) ──
    # Character body zone: center columns, mid-height only
    body_zone_y = np.clip((yy - 0.15) / 0.65, 0, 1) * np.clip((0.80 - yy) / 0.20, 0, 1)  # fade out near floor
    body_zone_x = np.clip((xx - 0.20) / 0.20, 0, 1) * np.clip((0.80 - xx) / 0.20, 0, 1)  # fade out at edges
    body_weight = (body_zone_y * body_zone_x).astype(np.float32)
    # Luminance-based ambient: brighter pixels get more base ambient
    ambient_lum = np.clip((gray - 0.35) / 0.55, 0, 1) ** 2.5 * 0.10
    ambient = ambient_lum * body_weight

    # ── 2. HERO: Cyber visor (red/orange glow, upper face region) ──
    visor_zone = (yy > 0.22) & (yy < 0.42) & (xx > 0.35) & (xx < 0.65)
    visor_px = ((r > 0.60) & (r > g * 1.35) & visor_zone).astype(np.float32)
    visor = make_gradient_mask(visor_px, px * 0.012, px * 0.04, peak=0.85, falloff_weight=0.55)

    # ── 3. HERO: Earring & collar highlights ──
    collar_zone = (yy > 0.28) & (yy < 0.50) & (xx > 0.38) & (xx < 0.68)
    collar_px = ((gray > 0.75) & (r > 0.60) & collar_zone).astype(np.float32)
    collar = make_gradient_mask(collar_px, px * 0.008, px * 0.025, peak=0.60, falloff_weight=0.40)

    # ── 4. MID: Green Nichirin Katana sheath & hilt ──
    katana_zone = (yy > 0.38) & (yy < 0.72)
    # Green accents (checkered pattern colors)
    green_katana = ((g > 0.42) & (g > r * 1.10) & (g > b * 0.85) & katana_zone).astype(np.float32)
    katana_mask = make_gradient_mask(green_katana, px * 0.010, px * 0.030, peak=0.65, falloff_weight=0.45)

    # ── 5. MID: Character body outline (rim-light on edges) ──
    # Edge detect on character silhouette
    edges_raw = cv2.Canny(img8, 60, 130).astype(np.float32) / 255.0
    # Only bright-ish edges (not pure black outlines on dark background)
    char_body_zone = (yy > 0.18) & (yy < 0.82) & (xx > 0.25) & (xx < 0.75)
    rim_px = (edges_raw * (gray > 0.35)) * char_body_zone
    rim = gblur(rim_px, px * 0.006) * 0.30

    # ── 6. SUPPRESS: Street lamps — HARD suppress, they should not glow ──
    # Bright yellow/warm blobs in background (outside character center zone)
    char_center_zone = (yy > 0.18) & (yy < 0.90) & (xx > 0.30) & (xx < 0.70)
    lamp_candidate = (gray > 0.72) & (r > 0.50) & ~char_center_zone
    # NO blur — raw pixel only, capped at 0.04 (barely imperceptible)
    lamp_cap = lamp_candidate.astype(np.float32) * 0.04

    # ── 7. SUPPRESS: Shoes — absolute minimum, raw pixels only ──
    shoe_zone = (yy > 0.80)
    shoe_px = ((g > 0.45) & (g > r * 1.15) & shoe_zone).astype(np.float32)
    shoes = shoe_px * 0.03  # raw pixel only, NO blur spread

    # ── 8. SUPPRESS: Floor — near zero, NO spreading  ──
    floor_zone = (yy > 0.75)
    # Only floor DOTS that are very bright and saturated (not the whole floor)
    floor_hsv = cv2.cvtColor(img8, cv2.COLOR_RGB2HSV).astype(np.float32)
    floor_sat = floor_hsv[..., 1] / 255.0
    # Floor scatter is colorful (high saturation) but should be almost invisible
    floor_bright = ((gray > 0.78) & floor_zone).astype(np.float32)
    floor = floor_bright * 0.025  # extremely dim

    # ── 9. SUPPRESS: Moon/sky orb — dim it, it should not bloom ──
    sky_bright = ((gray > 0.78) & (yy < 0.22)).astype(np.float32)
    moon_subtle = sky_bright * 0.08  # very subtle glow only

    # ── COMBINE ──
    core = ambient + visor + collar + katana_mask + rim + lamp_cap + shoes + floor + moon_subtle
    # Soft-cap: prevent any single region from going above 0.88
    core = np.clip(core, 0, 0.88)
    return core


def mask_darth_vader(img, s):
    """
    Vader + Ahsoka lightsaber duel.
    - Lightsaber blades = absolute hero (0.85 peak + strong falloff)
    - Red blade tip = slightly brighter (Vader)
    - Blue-white blade (Ahsoka) = slightly cooler peak (0.80)
    - Ground scatter / yellow explosion = max 0.07, NO spreading
    - Magma sparks = max 0.05
    """
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    px = min(h, w)

    # ── HERO: Any very bright core (blade cores) ──
    bright_core = (gray > 0.88).astype(np.float32)
    blade_hero = make_gradient_mask(bright_core, px * 0.015, px * 0.055, peak=0.85, falloff_weight=0.60)

    # ── HERO: Vader red blade edge ──
    vader_blade = ((r > 0.65) & (r > g * 1.9) & (r > b * 1.9) & (gray > 0.40)).astype(np.float32)
    vader_mask = make_gradient_mask(vader_blade, px * 0.012, px * 0.040, peak=0.78, falloff_weight=0.50)

    # ── HERO: Ahsoka blue-white blades ──
    ahsoka_px = ((b > 0.60) & (g > 0.55) & (gray > 0.60)).astype(np.float32)
    ahsoka_mask = make_gradient_mask(ahsoka_px, px * 0.012, px * 0.040, peak=0.80, falloff_weight=0.50)

    # ── SUPPRESS: Ground scatter / yellow explosion — absolute minimum ──
    ground_zone = np.zeros((h, w), np.float32)
    ground_zone[int(h * 0.52):, :] = 1.0
    # Yellow explosion area (high r+g, low b)
    yellow_blast = ((r > 0.50) & (g > 0.40) & (b < 0.30) & (ground_zone > 0)).astype(np.float32)
    # Raw pixel, no blur, cap at 0.06
    scatter = yellow_blast * 0.06

    # ── SUPPRESS: Magma / red sparks ground ──
    vader_ground = np.zeros((h, w), np.float32)
    vader_ground[int(h * 0.58):, :int(w * 0.52)] = 1.0
    magma = ((r > 0.55) & (g > 0.30) & (b < 0.25) & (vader_ground > 0)).astype(np.float32)
    magma_subtle = magma * 0.04

    core = blade_hero + vader_mask + ahsoka_mask + scatter + magma_subtle
    return np.clip(core, 0, 0.90)


def mask_your_name(img, s):
    """Your Name: Comet is hero. City pinpricks very subtle."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    yy = np.arange(h)[:, None] / float(h)
    px = min(h, w)

    sky_zone = (yy < 0.58)
    # Comet head (very bright)
    comet_head = ((gray > 0.82) & sky_zone).astype(np.float32)
    comet_hero = make_gradient_mask(comet_head, px * 0.020, px * 0.070, peak=0.85, falloff_weight=0.55)

    # Comet trail (medium brightness gradient)
    comet_trail_raw = np.clip((gray - 0.60) / 0.40, 0, 1) ** 2.0 * sky_zone * 0.35
    comet_trail = gblur(comet_trail_raw, px * 0.015)

    # City windows (bottom zone, tiny pinpricks, very subtle)
    city_zone = (yy >= 0.58) & (yy < 0.78)
    city_px = ((gray > 0.82) & city_zone).astype(np.float32)
    city = city_px * 0.12  # no spread

    # Character silhouette rim (Taki figure)
    char_zone = (yy > 0.65)
    edges = cv2.Canny(img8, 50, 110).astype(np.float32) / 255.0
    rim = gblur(edges * char_zone * (gray > 0.30), px * 0.005) * 0.20

    core = comet_hero + comet_trail + city + rim
    return np.clip(core, 0, 0.90)


def mask_edgerunners(img, s):
    """
    Edgerunners: Lucy's cyberware + David's collar = hero.
    Earth rim = subtle. Floor/shoes = minimal.
    """
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    yy = np.arange(h)[:, None] / float(h)
    px = min(h, w)

    char_zone = (yy > 0.55)

    # Hero: Cyberware — yellow collar (David)
    yellow_collar = ((r > 0.55) & (g > 0.50) & (b < 0.28) & char_zone).astype(np.float32)
    collar_mask = make_gradient_mask(yellow_collar, px * 0.012, px * 0.040, peak=0.75, falloff_weight=0.50)

    # Hero: Cyan spine implants (Lucy)
    cyan_spine = ((b > 0.55) & (g > 0.50) & (r < 0.42) & char_zone).astype(np.float32)
    cyan_mask = make_gradient_mask(cyan_spine, px * 0.010, px * 0.035, peak=0.70, falloff_weight=0.45)

    # Hero: Red arm/spine accents
    red_spine = ((r > 0.60) & (g < 0.22) & (b < 0.22) & char_zone).astype(np.float32)
    red_mask = make_gradient_mask(red_spine, px * 0.008, px * 0.025, peak=0.65, falloff_weight=0.40)

    # Earth limb glow (blue atmosphere arc)
    earth_zone = (yy > 0.42) & (yy < 0.65)
    earth_edges = cv2.Canny(img8, 70, 140).astype(np.float32) / 255.0
    earth_rim = gblur(earth_edges * earth_zone * (b > 0.35), px * 0.010) * 0.22

    # Suppress shoes/floor scatter — raw pixel, capped at 0.06
    floor_zone = (yy > 0.80)
    floor_px = ((gray > 0.65) & floor_zone).astype(np.float32)
    floor = floor_px * 0.05

    core = collar_mask + cyan_mask + red_mask + earth_rim + floor
    return np.clip(core, 0, 0.90)


def mask_gojo(img, s):
    """Gojo: Hollow Purple spark = hero. Lightning = mid. Eyes = accent."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    px = min(h, w)

    spark_px = (gray > 0.88).astype(np.float32)
    spark = make_gradient_mask(spark_px, px * 0.020, px * 0.075, peak=0.88, falloff_weight=0.60)

    lightning_px = ((r > 0.42) & (b > 0.52) & (g < 0.38) & (gray > 0.48)).astype(np.float32)
    lightning = make_gradient_mask(lightning_px, px * 0.012, px * 0.040, peak=0.40, falloff_weight=0.35)

    eyes_px = ((b > 0.62) & (r < 0.45) & (gray > 0.58)).astype(np.float32)
    eyes = make_gradient_mask(eyes_px, px * 0.010, px * 0.030, peak=0.55, falloff_weight=0.40)

    core = spark + lightning + eyes
    return np.clip(core, 0, 0.90)


def mask_spider_verse(img, s):
    """Spider-Verse: Miles neon accents = hero. Skyscraper windows = pinpricks."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    px = min(h, w)

    # Red spider-man accents
    red_px = ((r > 0.55) & (r > g * 1.80) & (r > b * 1.80)).astype(np.float32)
    red_mask = make_gradient_mask(red_px, px * 0.010, px * 0.035, peak=0.72, falloff_weight=0.45)

    # Neon skyscraper windows (highly saturated + bright)
    hsv = cv2.cvtColor(img8, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[..., 1] / 255.0
    neon_px = ((sat > 0.48) & (gray > 0.78)).astype(np.float32)
    neon = neon_px * 0.16  # raw pixel only, no spread

    core = red_mask + neon
    return np.clip(core, 0, 0.90)


def mask_interstellar(img, s):
    """Gargantua: Accretion disk gradient — smooth, no hard cuts."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    px = min(h, w)

    # Bright photon ring
    ring_px = (gray > 0.88).astype(np.float32)
    ring = make_gradient_mask(ring_px, px * 0.015, px * 0.060, peak=0.85, falloff_weight=0.55)

    # Orange/warm disk gradient
    disk_warm = np.clip((gray - 0.35) / 0.55, 0, 1) ** 2.0 * ((r > g) & (r > b)).astype(np.float32) * 0.60
    disk = gblur(disk_warm, px * 0.015)

    core = ring + disk
    return np.clip(core, 0, 0.90)


def mask_goku_ui(img, s):
    """Goku UI: Kamehameha sphere = hero. Silver-white aura halo = mid."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    px = min(h, w)

    sphere_px = (gray > 0.86).astype(np.float32)
    sphere = make_gradient_mask(sphere_px, px * 0.020, px * 0.080, peak=0.85, falloff_weight=0.60)

    aura_raw = np.clip((gray - 0.52) / 0.48, 0, 1) ** 2.5 * 0.30
    aura = gblur(aura_raw, px * 0.015)

    core = sphere + aura
    return np.clip(core, 0, 0.90)


def mask_aot(img, s):
    """AoT/Mikasa: Steel blade edge = hero. Fire/titan aura = mid."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    px = min(h, w)

    blade_px = (gray > 0.88).astype(np.float32)
    blade = make_gradient_mask(blade_px, px * 0.012, px * 0.045, peak=0.82, falloff_weight=0.55)

    fire_px = ((r > 0.62) & (g > 0.32) & (b < 0.22)).astype(np.float32)
    fire = make_gradient_mask(fire_px, px * 0.012, px * 0.040, peak=0.30, falloff_weight=0.35)

    core = blade + fire
    return np.clip(core, 0, 0.90)


def mask_generic(img, s):
    """Default fallback for packs without custom masks."""
    h, w = img.shape[:2]
    img8 = (img * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    px = min(h, w)
    bright_px = (gray > 0.80).astype(np.float32)
    hero = make_gradient_mask(bright_px, px * 0.015, px * 0.060, peak=0.80, falloff_weight=0.50)
    ambient = np.clip((gray - 0.70) / 0.30, 0, 1) ** 2.5 * 0.25
    return np.clip(hero + ambient, 0, 0.90)


# ──────────────────────── NEW PACKS DOWNLOAD + BUILD ──────────────────────

def download_wallpaper(url, out_path):
    import urllib.request
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(out_path, 'wb') as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def search_wallhaven(q, min_res='2560x1440', n=4):
    import urllib.request, urllib.parse, json
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = (f'https://wallhaven.cc/api/v1/search'
           f'?q={urllib.parse.quote(q)}&categories=011&purity=100'
           f'&sorting=favorites&atleast={min_res}')
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read()).get('data', [])
            return [(d['id'], d['path'], d.get('resolution',''), d.get('favorites',0)) for d in data[:n]]
    except Exception as e:
        print(f"  Wallhaven search error: {e}")
        return []


NEW_PACKS_QUERIES = [
    ('naruto', 'naruto rasengan fourth hokage orange'),
    ('chainsaw_man', 'chainsaw man denji power blood'),
    ('one_piece', 'one piece luffy gear fifth sun god'),
    ('evangelion', 'neon genesis evangelion unit 01 night'),
    ('blade_runner', 'blade runner 2049 ryan gosling neon rain'),
]


def build_new_packs_from_downloads():
    """Download top wallhaven hits for new packs then build them."""
    import os
    temp_dir = os.path.join(os.path.dirname(HERE), "temp_wallpapers")
    os.makedirs(temp_dir, exist_ok=True)

    new_pack_meta = {
        'naruto': {
            'name': 'Naruto: Rasengan',
            'desc': 'Naruto Uzumaki channeling his blazing Rasengan with Nine-Tails chakra.',
            'color': '#ff6600',
            'mask': mask_generic,
        },
        'chainsaw_man': {
            'name': 'Chainsaw Man: Denji',
            'desc': 'Denji unleashing chainsaw devil form with crimson blood and neon city backdrop.',
            'color': '#ff1a1a',
            'mask': mask_generic,
        },
        'one_piece': {
            'name': 'One Piece: Gear 5',
            'desc': 'Monkey D. Luffy in Sun God Nika Gear 5 form radiating divine lightning.',
            'color': '#ffd700',
            'mask': mask_goku_ui,  # similar energy sphere logic
        },
        'evangelion': {
            'name': 'Evangelion: Unit-01',
            'desc': 'Evangelion Unit-01 awakening in purple berserk mode.',
            'color': '#7700ff',
            'mask': mask_generic,
        },
        'blade_runner': {
            'name': 'Blade Runner 2049',
            'desc': 'K walks through neon-drenched Los Angeles 2049 rainy streets.',
            'color': '#00aaff',
            'mask': mask_generic,
        },
    }

    built = []
    for pack_id, query in NEW_PACKS_QUERIES:
        # Check if already downloaded
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            existing = os.path.join(temp_dir, f'{pack_id}{ext}')
            if os.path.exists(existing):
                print(f"  {pack_id}: already downloaded -> {existing}")
                img_path = existing
                break
        else:
            # Search and download
            results = search_wallhaven(query)
            if not results:
                print(f"  {pack_id}: No results from wallhaven, skipping")
                continue
            best = results[0]
            ext = os.path.splitext(best[1])[1] or '.jpg'
            img_path = os.path.join(temp_dir, f'{pack_id}{ext}')
            print(f"  {pack_id}: Downloading {best[1]} (fav={best[3]})")
            if not download_wallpaper(best[1], img_path):
                print(f"  {pack_id}: Download failed")
                continue
            print(f"  {pack_id}: Saved -> {img_path}")

        # Load and build pack
        bgr = cv2.imread(img_path)
        if bgr is None:
            print(f"  {pack_id}: Failed to load image")
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        meta = new_pack_meta[pack_id]
        assemble_pack(
            pack_id, meta['name'], meta['desc'], meta['color'],
            rgb, rgb, mask_fn=meta['mask']
        )
        built.append(pack_id)

    return built


def run_all():
    # ── A. Existing anime/movie packs with improved masks ──
    catalog = [
        {
            "id": "demon_slayer",
            "name": "Demon Slayer: Neo Tokyo",
            "desc": "Tanjiro in Neo-Tokyo with illuminated nichirin katana, cyber visor, and moonlit reflection.",
            "color": "#00ff9d",
            "land_img": "library/packs/demon_slayer/phone_land_base.jpg",
            "port_img": "library/packs/demon_slayer/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_demon_slayer
        },
        {
            "id": "darth_vader",
            "name": "Star Wars: Sith Lord",
            "desc": "Darth Vader vs Ahsoka lightsaber duel on volcanic world.",
            "color": "#ff0033",
            "land_img": "library/packs/darth_vader/phone_land_base.jpg",
            "port_img": "library/packs/darth_vader/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_darth_vader
        },
        {
            "id": "your_name",
            "name": "Your Name: Twilight Comet",
            "desc": "Taki on Tokyo rooftop gazing at the splitting Tiamat comet.",
            "color": "#5e72e4",
            "land_img": "library/packs/your_name/phone_land_base.jpg",
            "port_img": "library/packs/your_name/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_your_name
        },
        {
            "id": "edgerunners",
            "name": "Edgerunners: Moon",
            "desc": "Lucy and David on the moon with illuminated cyberware.",
            "color": "#00e5ff",
            "land_img": "library/packs/edgerunners/phone_land_base.jpg",
            "port_img": "library/packs/edgerunners/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_edgerunners
        },
        {
            "id": "gojo_purple",
            "name": "Jujutsu Kaisen: Gojo",
            "desc": "Gojo unleashing Hollow Purple with Six Eyes.",
            "color": "#bf00ff",
            "land_img": "library/packs/gojo_purple/phone_land_base.jpg",
            "port_img": "library/packs/gojo_purple/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_gojo
        },
        {
            "id": "spider_verse",
            "name": "Spider-Verse: Leap",
            "desc": "Miles Morales leap through neon Manhattan.",
            "color": "#ff1744",
            "land_img": "library/packs/spider_verse/phone_land_base.jpg",
            "port_img": "library/packs/spider_verse/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_spider_verse
        },
        {
            "id": "interstellar",
            "name": "Interstellar: Gargantua",
            "desc": "Supermassive black hole Gargantua with relativistic accretion disk.",
            "color": "#00e5ff",
            "land_img": "library/packs/interstellar/phone_land_base.jpg",
            "port_img": "library/packs/interstellar/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_interstellar
        },
        {
            "id": "goku_ui",
            "name": "Dragon Ball: Ultra Instinct",
            "desc": "Goku Kamehameha with divine Ultra Instinct energy.",
            "color": "#00d2ff",
            "land_img": "library/packs/goku_ui/phone_land_base.jpg",
            "port_img": "library/packs/goku_ui/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_goku_ui
        },
        {
            "id": "aot_mikasa",
            "name": "Attack on Titan: Wall Maria",
            "desc": "Mikasa Ackerman with gleaming ultrahard steel blades.",
            "color": "#ff3838",
            "land_img": "library/packs/aot_mikasa/phone_land_base.jpg",
            "port_img": "library/packs/aot_mikasa/phone_base.jpg",
            "land_focal": (0.5, 0.5), "port_focal": (0.5, 0.5),
            "mask": mask_aot
        },
    ]

    for item in catalog:
        land_path = os.path.join(ROOT, item["land_img"]) if not os.path.isabs(item["land_img"]) else item["land_img"]
        port_path = os.path.join(ROOT, item["port_img"]) if not os.path.isabs(item["port_img"]) else item["port_img"]
        # Try relative to HERE too
        if not os.path.exists(land_path):
            land_path = item["land_img"]
        if not os.path.exists(port_path):
            port_path = item["port_img"]

        land_bgr = cv2.imread(land_path)
        port_bgr = cv2.imread(port_path) if os.path.exists(port_path) else land_bgr
        if land_bgr is None:
            print(f"Skipping {item['id']}: land image not found at {land_path}")
            continue
        if port_bgr is None:
            port_bgr = land_bgr

        land_rgb = cv2.cvtColor(land_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        port_rgb = cv2.cvtColor(port_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        assemble_pack(
            item["id"], item["name"], item["desc"], item["color"],
            land_rgb, port_rgb,
            land_focal=item["land_focal"], port_focal=item["port_focal"],
            mask_fn=item["mask"]
        )

    # ── B. Download and build new packs ──
    print("\n=== Downloading & Building New Packs ===")
    new_built = build_new_packs_from_downloads()
    print(f"New packs built: {new_built}")

    # ── C. Update catalog index ──
    try:
        import render
        total = render.write_index()
        print(f"\nCatalogue updated: {total} total packs!")
    except Exception as e:
        print(f"render.write_index skipped: {e}")


if __name__ == "__main__":
    run_all()
