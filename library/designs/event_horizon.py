"""Supermassive black hole with gravitationally lensed relativistic accretion disk and photon ring."""
import numpy as np
import cv2
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Event Horizon"
DESC = "Supermassive black hole with relativistic accretion disk and gravitationally lensed photon sphere."
COLOR = "#00e5ff"


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s
    cx = w * 0.5
    # Center position: balanced for phone notch/clock and home screen icons
    cy = h * (0.44 if not sc.landscape else 0.50)

    # 1. Cosmic Void & Deep Space Nebula
    sc.base = vgrad(sc, (0.003, 0.005, 0.010), (0.008, 0.004, 0.015), 1.1)
    cosmic_dust = noise(sc, 160 * s, 0.015) + noise(sc, 70 * s, 0.010)
    sc.base += np.clip(cosmic_dust, 0, 1)[..., None] * np.array([0.15, 0.08, 0.35], dtype=np.float32)

    # 2. Deflected Starfield (Einstein Gravitational Lensing)
    n_stars = int(w * h / 4500)
    sx = sc.rng.uniform(0, w, n_stars)
    sy = sc.rng.uniform(0, h, n_stars)
    r_sing = (175 if not sc.landscape else 195) * s
    einstein_r = r_sing * 2.2

    dx = sx - cx
    dy = sy - cy
    dist_s = np.hypot(dx, dy)
    deflection = (einstein_r ** 2) / (dist_s + 1e-2)
    sx_def = np.clip(sx + dx / (dist_s + 1e-2) * deflection * 0.18, 0, w - 1).astype(int)
    sy_def = np.clip(sy + dy / (dist_s + 1e-2) * deflection * 0.18, 0, h - 1).astype(int)

    st = np.zeros((h, w), np.float32)
    valid = dist_s > r_sing * 1.08
    st[sy_def[valid], sx_def[valid]] = sc.rng.uniform(0.3, 1.0, valid.sum()) ** 2.5
    # Star glow
    st_layer = blur(st, 0.7 * s) * 2.2 + blur(st, 2.5 * s) * 0.6
    sc.base += st_layer[..., None] * np.array([0.85, 0.92, 1.0], dtype=np.float32)

    # 3. Coordinate Grids for Kerr Metric Lensing
    xx = sc.xx - cx
    yy = sc.yy - cy
    r = np.hypot(xx, yy)
    theta = np.arctan2(yy, xx)

    # Disk inclination tilt angle
    tilt_rad = np.deg2rad(-14.0)
    rx = xx * np.cos(tilt_rad) - yy * np.sin(tilt_rad)
    ry = xx * np.sin(tilt_rad) + yy * np.cos(tilt_rad)

    # Flattened disk coordinates
    disk_comp = 0.22  # perspective foreshortening of the accretion disk plane
    scaled_ry = ry / disk_comp
    r_disk = np.hypot(rx, scaled_ry)

    # Inner stable circular orbit (ISCO) & outer accretion boundary
    r_isco = r_sing * 1.35
    r_outer = r_sing * (4.8 if not sc.landscape else 5.4)

    # Relativistic Doppler beaming (approaching plasma is hotter and significantly brighter)
    doppler = np.clip(1.0 - 0.75 * (rx / (r + 1e-2)), 0.15, 2.2)

    # Concentric plasma striations (differential Keplerian rotation)
    kepler_striations = (
        np.sin(r_disk / (12.0 * s) * np.pi) * 0.15 +
        np.sin(r_disk / (4.5 * s) * np.pi) * 0.10 +
        np.sin(theta * 8.0 + r_disk / (20.0 * s)) * 0.12
    )

    # Primary Accretion Disk profile
    disk_falloff = np.clip((r_disk - r_isco) / (r_sing * 0.25), 0, 1) * np.clip((r_outer - r_disk) / (r_outer - r_isco), 0, 1) ** 1.8
    disk_intensity = disk_falloff * (1.0 + kepler_striations) * doppler

    # Lensed Primary Arch (back of the disk bent over the top of the event horizon)
    # Lensing equation creates a secondary image appearing as a ring/arch above and below
    arch_dist = np.abs(r - r_sing * 1.75) / (r_sing * 0.65)
    arch_mask = np.clip(1.0 - arch_dist, 0, 1) ** 2.0
    # Modulate arch by disk rotation and Doppler effect
    arch_intensity = arch_mask * np.clip((r - r_sing * 1.08) / (r_sing * 0.15), 0, 1) * doppler * 0.85
    # The lensed arch is cut by the foreground horizon
    arch_intensity *= (1.0 + np.sin(r / (10.0 * s) * np.pi) * 0.1)

    # Combine disk and gravitational lensed arch
    plasma_core = np.maximum(disk_intensity, arch_intensity)

    # 4. Photon Sphere Ring (razor-thin, blindingly bright orbit where light orbits the hole)
    photon_ring = np.exp(-(((r - r_sing * 1.06) / (2.0 * s)) ** 2)) * 1.6

    # 5. Relativistic Polar Jet Beams
    jet_angle = tilt_rad + np.pi / 2.0
    jet_x = xx * np.cos(jet_angle) - yy * np.sin(jet_angle)
    jet_y = xx * np.sin(jet_angle) + yy * np.cos(jet_angle)
    jet_width = r_sing * 0.12 * (1.0 + np.abs(jet_y) / (h * 0.35))
    jet_beam = (
        np.exp(-((jet_x / (jet_width + 1e-2)) ** 2)) *
        np.exp(-np.abs(jet_y) / (h * 0.45)) *
        (np.abs(jet_y) > r_sing * 0.8)
    )

    # 6. Event Horizon Shadow (Singularity absorbs all light inside r_sing)
    shadow = np.clip((r - r_sing) / (2.2 * s), 0, 1)

    # 7. Light Layer Assembly (Aura color channel)
    sc.light += glow(plasma_core, s, tight=1.2, wide=0.8) * 0.95
    sc.light += photon_ring * 1.2 + blur(photon_ring, 6 * s) * 0.7
    sc.light += glow(jet_beam, s, tight=1.0, wide=0.6) * 0.8

    # Apply strict singularity shadow
    sc.light *= shadow

    # Ambient illumination in surrounding gas & dust
    sc.base += blur(sc.light, 70 * s)[..., None] * np.array([0.08, 0.05, 0.12], dtype=np.float32)
    sc.base *= shadow[..., None]
    sc.base += grain(sc, 0.005)
