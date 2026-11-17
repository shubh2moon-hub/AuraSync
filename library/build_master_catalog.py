"""Builds high-quality Anime, Movie, and Sci-Fi Live Wallpapers with strict brightness hierarchy."""
import os, sys, json
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from toolkit import PHONE, PHONE_LAND, PC, _jpg, blur

HERE = os.path.dirname(os.path.abspath(__file__))
PACKS_DIR = os.path.join(HERE, "packs")


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

    cropped = img[y0:y0 + new_h, x0:x0 + new_w]
    return cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_AREA if new_w > target_w else cv2.INTER_LANCZOS4)


def assemble_pack(pack_id, name, desc, default_color,
                  img_land_src, img_port_src=None,
                  land_focal=(0.5, 0.5), port_focal=(0.5, 0.5),
                  mask_fn=None):
    out_dir = os.path.join(PACKS_DIR, pack_id)
    os.makedirs(out_dir, exist_ok=True)
    col = np.array([int(default_color[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255

    if img_port_src is None:
        img_port_src = img_land_src

    def process_layer(img_rgb01):
        h, w = img_rgb01.shape[:2]
        s = min(w, h) / 1080.0
        if mask_fn is not None:
            core = mask_fn(img_rgb01, s)
        else:
            gray = cv2.cvtColor((img_rgb01 * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
            core = np.clip((gray - 0.78) / 0.22, 0, 1) ** 2.2 * 0.7

        core = np.clip(core, 0, 1)

        # Controlled, tight optical glow: avoids blowing out backgrounds and flooding screen
        light_layer = (
            core * 0.85 +
            blur(core, 2.0 * s) * 0.35 +
            blur(core, 6.5 * s) * 0.18 +
            blur(core, 18.0 * s) * 0.07
        )
        light_layer = np.clip(light_layer, 0, 1)

        # Keep base rich and high-contrast
        base_layer = img_rgb01 * (1.0 - core[..., None] * 0.20)
        return base_layer, light_layer

    # 1. Native Phone Portrait
    pw, ph = PHONE
    cropped_p = crop_to_aspect(img_port_src, pw, ph, port_focal[0], port_focal[1])
    base_p, light_p = process_layer(cropped_p)
    _jpg(os.path.join(out_dir, "phone_base.jpg"), base_p)
    _jpg(os.path.join(out_dir, "phone_light.jpg"), gray01=light_p)

    prev_p_sz = (360, round(ph * 360 / pw))
    bp_prev = cv2.resize(base_p, prev_p_sz, interpolation=cv2.INTER_AREA)
    lp_prev = cv2.resize(light_p, prev_p_sz, interpolation=cv2.INTER_AREA)
    comp_p = np.clip(bp_prev + lp_prev[..., None] * col * 0.80 + (lp_prev[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "phone_preview.jpg"), comp_p, q=88)

    # 2. Native Phone Landscape
    lw, lh = PHONE_LAND
    cropped_l = crop_to_aspect(img_land_src, lw, lh, land_focal[0], land_focal[1])
    base_l, light_l = process_layer(cropped_l)
    _jpg(os.path.join(out_dir, "phone_land_base.jpg"), base_l)
    _jpg(os.path.join(out_dir, "phone_land_light.jpg"), gray01=light_l)

    prev_l_sz = (round(lw * 200 / lh), 200)
    bl_prev = cv2.resize(base_l, prev_l_sz, interpolation=cv2.INTER_AREA)
    ll_prev = cv2.resize(light_l, prev_l_sz, interpolation=cv2.INTER_AREA)
    comp_l = np.clip(bl_prev + ll_prev[..., None] * col * 0.80 + (ll_prev[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "phone_land_preview.jpg"), comp_l, q=88)

    # 3. PC Desktop (3840 x 2160)
    pcw, pch = PC
    cropped_pc = crop_to_aspect(img_land_src, pcw, pch, land_focal[0], land_focal[1])
    base_pc, light_pc = process_layer(cropped_pc)
    _jpg(os.path.join(out_dir, "pc_base.jpg"), base_pc)
    _jpg(os.path.join(out_dir, "pc_light.jpg"), gray01=light_pc)

    pc_prev_sz = (960, 540)
    bpc_prev = cv2.resize(base_pc, pc_prev_sz, interpolation=cv2.INTER_AREA)
    lpc_prev = cv2.resize(light_pc, pc_prev_sz, interpolation=cv2.INTER_AREA)
    comp_pc = np.clip(bpc_prev + lpc_prev[..., None] * col * 0.80 + (lpc_prev[..., None] ** 2) * 0.20, 0, 1)
    _jpg(os.path.join(out_dir, "pc_preview.jpg"), comp_pc, q=88)

    # Master legacy files
    _jpg(os.path.join(out_dir, "master_base.jpg"), base_pc)
    _jpg(os.path.join(out_dir, "master_light.jpg"), gray01=light_pc)
    _jpg(os.path.join(out_dir, "master_base_small.jpg"), cv2.resize(base_pc, (1284, round(pch * 1284 / pcw)), interpolation=cv2.INTER_AREA), q=90)
    _jpg(os.path.join(out_dir, "master_light_small.jpg"), gray01=cv2.resize(light_pc, (1284, round(pch * 1284 / pcw)), interpolation=cv2.INTER_AREA), q=90)

    # 4. Meta JSON
    meta = {
        "id": pack_id,
        "name": name,
        "description": desc,
        "credits": "Anime & Movie Live Wallpaper Edition",
        "license": "Personal live wallpaper synchronization",
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

    print(f"-> Refined pack: {pack_id} ({name})")


# Mask Functions with Dynamic Hierarchy

def mask_demon_slayer(img, s):
    """Tanjiro: visor & katana are heroes. Background lamps completely excluded. Shoes & floor minimized."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    yy = np.arange(h)[:, None] / float(h)
    xx = np.arange(w)[None, :] / float(w)

    # 1. Hero: Tanjiro's cyber visor (sharp red/orange eye glow)
    visor_zone = (yy > 0.28) & (yy < 0.40) & (xx > 0.38) & (xx < 0.52)
    visor = (r > 0.65) & (r > g * 1.4) & visor_zone

    # 2. Hero: Checkered Nichirin Katana Sheath & hilt
    katana_zone = (yy > 0.40) & (yy < 0.70)
    green_katana = (g > 0.45) & (g > r * 1.15) & (g > b * 0.9) & katana_zone

    # 3. Collar trim & earring (subtle accent)
    collar_zone = (yy > 0.32) & (yy < 0.46) & (xx > 0.40) & (xx < 0.65)
    collar = (gray > 0.78) & collar_zone

    # 4. Moon: soft subtle ambient highlight
    moon_zone = (yy < 0.22) & (xx > 0.35) & (xx < 0.65)
    moon = np.clip((gray - 0.75) / 0.25, 0, 1) ** 2.0 * moon_zone * 0.30

    # 5. Background street lamps: 0.0 (COMPLETELY EXCLUDED so background remains dark & legible)

    # 6. Shoes: drastically reduced to faint seam accents (< 0.10)
    shoe_zone = (yy > 0.78)
    shoes = (g > 0.5) & (g > r * 1.2) & shoe_zone
    shoes_subtle = shoes.astype(np.float32) * 0.08

    # 7. Floor stardust / dots: reduced to near zero (< 0.04)
    floor_zone = (yy > 0.70)
    floor_dots = (gray > 0.78) & floor_zone
    floor_subtle = floor_dots.astype(np.float32) * 0.03

    core = (
        visor.astype(np.float32) * 0.85 +
        green_katana.astype(np.float32) * 0.75 +
        collar.astype(np.float32) * 0.35 +
        moon +
        shoes_subtle +
        floor_subtle
    )
    return np.clip(core, 0, 1)


def mask_darth_vader(img, s):
    """Vader: lightsabers are the dominant hero lights. Ground scatter & magma minimized."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]

    # 1. Hero: Lightsaber blades (sharp, intense core)
    blade_core = (gray > 0.90)
    # Vader's blade red edge
    vader_blade = (r > 0.70) & (r > g * 1.8) & (r > b * 1.8) & (gray > 0.45)
    # Ahsoka's twin white-blue blades
    ahsoka_blade = (b > 0.65) & (g > 0.60) & (gray > 0.65) & (np.arange(w)[None, :] > int(w * 0.45))

    lightsabers = np.clip(blade_core.astype(np.float32) * 0.90 +
                          vader_blade.astype(np.float32) * 0.80 +
                          ahsoka_blade.astype(np.float32) * 0.85, 0, 1)

    # 2. Ground scatter: drastically reduced to minimum (0.08)
    ground_zone = np.zeros_like(gray)
    ground_zone[int(h * 0.55):, :] = 1.0
    ground_scatter = ((r > 0.45) | (b > 0.45)) & (gray > 0.40) & (gray <= 0.90) & (ground_zone > 0)
    scatter_subtle = ground_scatter.astype(np.float32) * 0.08

    # 3. Magma / sparks under Vader: reduced to absolute minimum (0.06)
    vader_ground_zone = np.zeros_like(gray)
    vader_ground_zone[int(h * 0.60):, :int(w * 0.50)] = 1.0
    magma_sparks = (r > 0.55) & (g > 0.35) & (b < 0.25) & (vader_ground_zone > 0)
    magma_minimal = magma_sparks.astype(np.float32) * 0.06

    core = np.clip(lightsabers + scatter_subtle + magma_minimal, 0, 1)
    return core


def mask_your_name(img, s):
    """Your Name: Tiamat comet head & primary tail are hero. Distant skyline is subtle pinpricks."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    yy = np.arange(h)[:, None] / float(h)

    # Hero: Splitting Tiamat comet head & primary streak
    sky_zone = (yy < 0.55)
    comet_head = (gray > 0.85) & sky_zone
    comet_trail = np.clip((gray - 0.65) / 0.35, 0, 1) ** 2.2 * sky_zone * 0.40

    # City buildings: delicate subtle window pinpricks only
    city_zone = (yy >= 0.55) & (yy < 0.72)
    city_windows = (gray > 0.85) & city_zone
    city_subtle = city_windows.astype(np.float32) * 0.15

    core = np.clip(comet_head.astype(np.float32) * 0.85 + comet_trail + city_subtle, 0, 1)
    return core


def mask_edgerunners(img, s):
    """Edgerunners: Lucy's cyberware spine & David's collar LED are hero. Earth rim is subtle."""
    h, w = img.shape[:2]
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    yy = np.arange(h)[:, None] / float(h)

    # Hero: Lucy's spine & David's collar
    char_zone = (yy > 0.60)
    yellow_collar = (r > 0.55) & (g > 0.55) & (b < 0.25) & char_zone
    cyan_spine = (b > 0.55) & (g > 0.55) & (r < 0.40) & char_zone
    spine_red = (r > 0.60) & (g < 0.20) & (b < 0.20) & char_zone
    chars = (yellow_collar | cyan_spine | spine_red).astype(np.float32) * 0.75

    # Earth limb: razor-thin edge, subtle accent
    edges = cv2.Canny((gray * 255).astype(np.uint8), 80, 160).astype(np.float32) / 255.0
    earth_rim_zone = (yy > 0.45) & (yy < 0.62)
    earth_rim = edges * earth_rim_zone * (gray > 0.35) * 0.20

    core = np.clip(chars + earth_rim, 0, 1)
    return core


def mask_gojo(img, s):
    """Gojo: Hollow Purple spark & lightning are hero."""
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    spark = (gray > 0.90)
    lightning = (r > 0.45) & (b > 0.55) & (g < 0.35) & (gray > 0.50)
    eyes = (b > 0.65) & (r < 0.45) & (gray > 0.60)
    core = spark.astype(np.float32) * 0.85 + lightning.astype(np.float32) * 0.35 + eyes.astype(np.float32) * 0.55
    return np.clip(core, 0, 1)


def mask_spider_verse(img, s):
    """Spider-Verse: Miles' sneakers/hood are hero. Skyscraper windows are subtle pinpricks."""
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    red_accents = (r > 0.55) & (r > g * 1.8) & (r > b * 1.8)
    hsv = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[..., 1] / 255.0
    neon_spires = (sat > 0.45) & (gray > 0.80)
    core = red_accents.astype(np.float32) * 0.70 + neon_spires.astype(np.float32) * 0.18
    return np.clip(core, 0, 1)


def mask_interstellar(img, s):
    """Gargantua: Relativistic accretion disk and photon ring."""
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    disk = np.clip((gray - 0.35) / 0.65, 0, 1) ** 1.8 * 0.80
    return disk


def mask_goku_ui(img, s):
    """Goku: Kamehameha sphere core is hero."""
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    sphere = (gray > 0.88)
    aura = np.clip((gray - 0.55) / 0.45, 0, 1) ** 2.0 * 0.35
    return np.clip(sphere.astype(np.float32) * 0.85 + aura, 0, 1)


def mask_aot(img, s):
    """Mikasa: Ultrahard steel blade razor edge is hero."""
    gray = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    blade_edge = (gray > 0.90)
    fire = (r > 0.65) & (g > 0.35) & (b < 0.20)
    return np.clip(blade_edge.astype(np.float32) * 0.80 + fire.astype(np.float32) * 0.20, 0, 1)


def run_all():
    catalog = [
        {
            "id": "demon_slayer",
            "name": "Demon Slayer: Neo Tokyo",
            "desc": "Tanjiro in Neo-Tokyo with illuminated nichirin katana, cyber visor, and moonlit reflection.",
            "color": "#00ff9d",
            "land_img": "library/packs/demon_slayer/phone_land_base.jpg",
            "port_img": "library/packs/demon_slayer/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_demon_slayer
        },
        {
            "id": "darth_vader",
            "name": "Star Wars: Sith Lord",
            "desc": "Darth Vader on volcanic world with glowing red lightsaber and burning embers.",
            "color": "#ff0033",
            "land_img": "library/packs/darth_vader/phone_land_base.jpg",
            "port_img": "library/packs/darth_vader/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_darth_vader
        },
        {
            "id": "your_name",
            "name": "Your Name: Twilight Comet",
            "desc": "Taki on Tokyo rooftop gazing at the splitting Tiamat comet and meteor shower.",
            "color": "#5e72e4",
            "land_img": "library/packs/your_name/phone_land_base.jpg",
            "port_img": "library/packs/your_name/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_your_name
        },
        {
            "id": "edgerunners",
            "name": "Edgerunners: Moon",
            "desc": "Lucy and David on the moon gazing at Earth with illuminated cyberware and atmospheric sunrise.",
            "color": "#00e5ff",
            "land_img": "library/packs/edgerunners/phone_land_base.jpg",
            "port_img": "library/packs/edgerunners/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_edgerunners
        },
        {
            "id": "gojo_purple",
            "name": "Jujutsu Kaisen: Gojo",
            "desc": "Gojo Satoru unleashing Hollow Purple with radiant Six Eyes and cursed energy.",
            "color": "#bf00ff",
            "land_img": "library/packs/gojo_purple/phone_land_base.jpg",
            "port_img": "library/packs/gojo_purple/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_gojo
        },
        {
            "id": "spider_verse",
            "name": "Spider-Verse: Leap",
            "desc": "Miles Morales What\'s Up Danger leap inverted through neon Manhattan skyscrapers.",
            "color": "#ff1744",
            "land_img": "library/packs/spider_verse/phone_land_base.jpg",
            "port_img": "library/packs/spider_verse/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_spider_verse
        },
        {
            "id": "interstellar",
            "name": "Interstellar: Gargantua",
            "desc": "Supermassive black hole Gargantua with glowing relativistic accretion disk and photon ring.",
            "color": "#00e5ff",
            "land_img": "library/packs/interstellar/phone_land_base.jpg",
            "port_img": "library/packs/interstellar/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_interstellar
        },
        {
            "id": "goku_ui",
            "name": "Dragon Ball: Ultra Instinct",
            "desc": "Goku unleashing divine Ultra Instinct Kamehameha with swirling celestial energy.",
            "color": "#00d2ff",
            "land_img": "library/packs/goku_ui/phone_land_base.jpg",
            "port_img": "library/packs/goku_ui/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_goku_ui
        },
        {
            "id": "aot_mikasa",
            "name": "Attack on Titan: Wall Maria",
            "desc": "Mikasa Ackerman soaring over Wall Maria with gleaming ultrahard steel blades.",
            "color": "#ff3838",
            "land_img": "library/packs/aot_mikasa/phone_land_base.jpg",
            "port_img": "library/packs/aot_mikasa/phone_base.jpg",
            "land_focal": (0.5, 0.5),
            "port_focal": (0.5, 0.5),
            "mask": mask_aot
        }
    ]

    for item in catalog:
        land_bgr = cv2.imread(item["land_img"])
        port_bgr = cv2.imread(item["port_img"]) if item.get("port_img") else land_bgr
        if land_bgr is None or port_bgr is None:
            print(f"Skipping {item['id']}: image not found")
            continue
        land_rgb = cv2.cvtColor(land_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        port_rgb = cv2.cvtColor(port_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

        assemble_pack(
            item["id"], item["name"], item["desc"], item["color"],
            land_rgb, port_rgb,
            land_focal=item["land_focal"], port_focal=item["port_focal"],
            mask_fn=item["mask"]
        )

    import render
    total = render.write_index()
    print(f"\nRefined master library catalogue updated: {total} total packs!")


if __name__ == "__main__":
    run_all()
