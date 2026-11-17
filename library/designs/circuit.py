"""Circuit board: futuristic neural processor motherboard with dense micro-trace buses,
SMD components, beveled heatspreader SoC, vias, and illuminated quantum core.
"""
import numpy as np
import cv2
from toolkit import Scene, blur, glow, lines, polys, vgrad, noise, grain

NAME = "Circuit"
DESC = "Futuristic cybernetic PCB with dense glowing micro-buses and neural SoC processor."
COLOR = "#00e5ff"

DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def make_bus(start, d, steps, seg, rng):
    """Clean 45-degree Manhattan/octilinear path."""
    pts = [start]
    x, y = start
    for _ in range(steps):
        L = seg * rng.uniform(0.7, 1.8)
        dx, dy = DIRS[d]
        norm = np.hypot(dx, dy)
        x, y = x + dx / norm * L, y + dy / norm * L
        pts.append((x, y))
        r = rng.random()
        if r < 0.4:
            d = (d + 1) % 8
        elif r < 0.8:
            d = (d - 1) % 8
    return pts


def offset_path(pts, offset_dist):
    """Parallel offset for multi-lane bus."""
    p = np.asarray(pts, np.float64)
    out = []
    for i in range(len(p)):
        a = p[max(i - 1, 0)]
        b = p[min(i + 1, len(p) - 1)]
        t = b - a
        norm = np.linalg.norm(t) + 1e-9
        t /= norm
        nrm = np.array([-t[1], t[0]])
        if 0 < i < len(p) - 1:
            t1 = p[i] - p[i - 1]; t1 /= np.linalg.norm(t1) + 1e-9
            t2 = p[i + 1] - p[i]; t2 /= np.linalg.norm(t2) + 1e-9
            n1 = np.array([-t1[1], t1[0]]); n2 = np.array([-t2[1], t2[0]])
            m = n1 + n2; m_norm = np.linalg.norm(m) + 1e-9
            m /= m_norm
            scale = 1.0 / max(np.dot(m, n1), 0.35)
            nrm = m * min(scale, 1.8)
        out.append(tuple(p[i] + nrm * offset_dist))
    return out


def draw(sc: Scene):
    w, h, s = sc.w, sc.h, sc.s

    # 1. Dark matte PCB substrate with fiberglass weave & ground hatch pattern
    sc.base = vgrad(sc, (0.012, 0.022, 0.026), (0.005, 0.012, 0.016), 1.0)
    sc.base += (noise(sc, 1.5 * s, 0.005) + noise(sc, 18 * s, 0.007))[..., None]

    # PCB ground copper hatch (diagonal crosshatch mesh beneath translucent solder mask)
    grid_spacing = int(sc.px(24))
    if grid_spacing >= 8:
        diag = ((sc.xx + sc.yy) % grid_spacing < sc.px(1.2)) | ((sc.xx - sc.yy) % grid_spacing < sc.px(1.2))
        hatch = diag.astype(np.float32) * 0.028
        sc.base += hatch[..., None] * np.array([0.1, 0.25, 0.22], dtype=np.float32)

    # Layers for copper traces, lit traces, vias, and components
    copper_dark = np.zeros((h, w), np.float32)    # unlit routed copper (dim metallic green/gold)
    copper_lit = np.zeros((h, w), np.float32)     # energized traces (white-hot core for AuraSync)
    solder_pads = np.zeros((h, w), np.float32)    # circular and octagonal component pads
    via_holes = np.zeros((h, w), np.float32)      # dark drill holes inside vias
    smd_caps = []                                 # (x, y, w, h, angle)

    # 2. Main Chips Layout
    chips = []
    if not sc.landscape:
        # Portrait: Dominant Neural SoC in upper-center (balanced for phone icons/dock)
        soc_w, soc_h = sc.px(300), sc.px(300)
        chips.append({"cx": w * 0.5, "cy": h * 0.42, "w": soc_w, "h": soc_h, "is_soc": True})
        # Satellite memory/co-processor modules
        chips.append({"cx": w * 0.22, "cy": h * 0.18, "w": sc.px(140), "h": sc.px(110), "is_soc": False})
        chips.append({"cx": w * 0.78, "cy": h * 0.20, "w": sc.px(130), "h": sc.px(150), "is_soc": False})
        chips.append({"cx": w * 0.24, "cy": h * 0.72, "w": sc.px(150), "h": sc.px(130), "is_soc": False})
        chips.append({"cx": w * 0.76, "cy": h * 0.68, "w": sc.px(140), "h": sc.px(120), "is_soc": False})
    else:
        # Landscape: Wide motherboard layout with dual main processors and bridge
        chips.append({"cx": w * 0.42, "cy": h * 0.48, "w": sc.px(320), "h": sc.px(320), "is_soc": True})
        chips.append({"cx": w * 0.75, "cy": h * 0.46, "w": sc.px(240), "h": sc.px(220), "is_soc": False})
        chips.append({"cx": w * 0.18, "cy": h * 0.35, "w": sc.px(180), "h": sc.px(140), "is_soc": False})
        chips.append({"cx": w * 0.22, "cy": h * 0.72, "w": sc.px(160), "h": sc.px(130), "is_soc": False})
        chips.append({"cx": w * 0.88, "cy": h * 0.28, "w": sc.px(140), "h": sc.px(130), "is_soc": False})

    # 3. Dense Parallel Bus Routing
    num_buses = 32 if sc.landscape else 26
    for b in range(num_buses):
        # 70% of buses emerge cleanly from chips
        if sc.rng.random() < 0.72 and chips:
            chip = chips[sc.rng.integers(len(chips))]
            cx, cy, cw, ch = chip["cx"], chip["cy"], chip["w"], chip["h"]
            side = sc.rng.integers(4)
            # 0: right, 1: bottom, 2: left, 3: top
            d = [0, 2, 4, 6][side]
            if side == 0:
                start = (cx + cw / 2 + sc.px(8), cy + sc.rng.uniform(-0.35, 0.35) * ch)
            elif side == 1:
                start = (cx + sc.rng.uniform(-0.35, 0.35) * cw, cy + ch / 2 + sc.px(8))
            elif side == 2:
                start = (cx - cw / 2 - sc.px(8), cy + sc.rng.uniform(-0.35, 0.35) * ch)
            else:
                start = (cx + sc.rng.uniform(-0.35, 0.35) * cw, cy - ch / 2 - sc.px(8))
        else:
            start = (sc.rng.uniform(0.05, 0.95) * w, sc.rng.uniform(0.05, 0.95) * h)
            d = int(sc.rng.integers(8))

        steps = int(sc.rng.integers(5, 11))
        seg_len = sc.px(sc.rng.uniform(70, 140))
        path = make_bus(start, d, steps, seg_len, sc.rng)

        # Multi-lane micro-bus: 4 to 8 parallel lines
        lanes = int(sc.rng.choice([3, 4, 6, 8]))
        gap = sc.px(sc.rng.uniform(6.5, 9.0))
        trace_w = max(1.2 * s, 1.6)

        is_high_speed_bus = sc.rng.random() < 0.65
        for k in range(lanes):
            offset_dist = (k - (lanes - 1) / 2.0) * gap
            lane = offset_path(path, offset_dist)

            # Draw copper trace
            lines(sc, [lane], trace_w, 1.0, copper_dark)

            # Lit trace for glowing AuraSync channel
            if is_high_speed_bus:
                # Hot center channel or alternating data lines
                intensity = sc.rng.uniform(0.7, 1.0) if (k % 2 == 0 or lanes <= 4) else 0.35
                lines(sc, [lane], trace_w * 0.85, intensity, copper_lit)

            # Terminating test point / via pad at the end of the line
            ex, ey = lane[-1]
            if 0 <= ex < w and 0 <= ey < h:
                pad_r = sc.px(sc.rng.uniform(4.5, 6.5))
                ang = np.linspace(0, 2 * np.pi, 16)
                ring = [(ex + pad_r * np.cos(a), ey + pad_r * np.sin(a)) for a in ang]
                lines(sc, [ring], 1.8 * s, 1.0, solder_pads)
                # Drill hole in center
                hole_r = pad_r * 0.45
                hole_pts = [(ex + hole_r * np.cos(a), ey + hole_r * np.sin(a)) for a in ang]
                polys(sc, [hole_pts], 1.0, via_holes)

                if is_high_speed_bus and sc.rng.random() < 0.5:
                    lines(sc, [ring], 1.5 * s, 0.9, copper_lit)

    # 4. Dense via farm arrays and serpentine meander delay lines
    # Motherboards have distinctive rectangular grids of stitching vias
    num_via_farms = 8 if sc.landscape else 6
    for _ in range(num_via_farms):
        vx = sc.rng.uniform(0.1, 0.9) * w
        vy = sc.rng.uniform(0.1, 0.9) * h
        cols, rows = sc.rng.integers(2, 6), sc.rng.integers(2, 6)
        v_spacing = sc.px(16)
        for r_idx in range(rows):
            for c_idx in range(cols):
                px = vx + c_idx * v_spacing
                py = vy + r_idx * v_spacing
                if 0 <= px < w and 0 <= py < h:
                    pr = sc.px(3.5)
                    ang = np.linspace(0, 2 * np.pi, 12)
                    ring = [(px + pr * np.cos(a), py + pr * np.sin(a)) for a in ang]
                    lines(sc, [ring], 1.4 * s, 0.8, solder_pads)
                    polys(sc, [[(px + pr * 0.4 * np.cos(a), py + pr * 0.4 * np.sin(a)) for a in ang]], 1.0, via_holes)

    # 5. Composite traces and pads onto base layer with realistic copper/gold color
    sc.base += copper_dark[..., None] * np.array([0.08, 0.16, 0.14], dtype=np.float32)
    sc.base += solder_pads[..., None] * np.array([0.22, 0.20, 0.12], dtype=np.float32)  # Gold/ENIG immersion pads
    sc.base *= (1.0 - via_holes[..., None] * 0.85)                                      # Dark via drill holes

    # 6. Render Detailed Chips (Package, Heatspreader, Neural Die, SMD Caps)
    chip_mask = np.zeros((h, w), np.float32)
    chip_light = np.zeros((h, w), np.float32)
    chip_diffuse = np.zeros((h, w, 3), np.float32)

    for chip in chips:
        cx, cy, cw, ch = chip["cx"], chip["cy"], chip["w"], chip["h"]
        is_soc = chip["is_soc"]

        # Pins / Solder Balls ringing the chip
        pin_len = sc.px(14)
        pin_w = max(1.5 * s, 1.8)
        pins_list = []
        # Top & Bottom pins
        npins_tb = int(cw / sc.px(10))
        for i in range(npins_tb):
            px = cx - cw / 2 + (i + 0.5) * cw / npins_tb
            pins_list.append([(px, cy - ch / 2 - pin_len), (px, cy - ch / 2)])
            pins_list.append([(px, cy + ch / 2), (px, cy + ch / 2 + pin_len)])
        # Left & Right pins
        npins_lr = int(ch / sc.px(10))
        for i in range(npins_lr):
            py = cy - ch / 2 + (i + 0.5) * ch / npins_lr
            pins_list.append([(cx - cw / 2 - pin_len, py), (cx - cw / 2, py)])
            pins_list.append([(cx + cw / 2, py), (cx + cw / 2 + pin_len, py)])

        lines(sc, pins_list, pin_w, 1.0, solder_pads)
        sc.base += lines(sc, pins_list, pin_w)[..., None] * np.array([0.28, 0.26, 0.16], dtype=np.float32)

        # Chip Body polygon
        p_tl = (cx - cw / 2, cy - ch / 2)
        p_tr = (cx + cw / 2, cy - ch / 2)
        p_br = (cx + cw / 2, cy + ch / 2)
        p_bl = (cx - cw / 2, cy + ch / 2)
        package_poly = [p_tl, p_tr, p_br, p_bl]
        polys(sc, [package_poly], 1.0, chip_mask)

        # Outer heatspreader / metallic frame
        bevel = sc.px(12)
        inner_poly = [
            (cx - cw / 2 + bevel, cy - ch / 2 + bevel),
            (cx + cw / 2 - bevel, cy - ch / 2 + bevel),
            (cx + cw / 2 - bevel, cy + ch / 2 - bevel),
            (cx - cw / 2 + bevel, cy + ch / 2 - bevel)
        ]

        # Draw metallic beveled frame on base
        frame_mask = np.zeros((h, w), np.float32)
        polys(sc, [package_poly], 1.0, frame_mask)
        polys(sc, [inner_poly], 0.0, frame_mask)
        # Metallic silver/titanium gradient
        sc.base += frame_mask[..., None] * np.array([0.07, 0.08, 0.09], dtype=np.float32)

        # Inner Die: dark ceramic core
        die_mask = np.zeros((h, w), np.float32)
        polys(sc, [inner_poly], 1.0, die_mask)
        # Deep matte obsidian silicon
        sc.base = sc.base * (1.0 - die_mask[..., None]) + die_mask[..., None] * np.array([0.015, 0.018, 0.022], dtype=np.float32)

        if is_soc:
            # SoC Neural Core: glowing central window, tensor core matrix, bus lines
            core_size = cw * 0.45
            core_rect = [
                (cx - core_size / 2, cy - core_size / 2),
                (cx + core_size / 2, cy - core_size / 2),
                (cx + core_size / 2, cy + core_size / 2),
                (cx - core_size / 2, cy + core_size / 2)
            ]
            lines(sc, [core_rect + [core_rect[0]]], 2.2 * s, 1.0, chip_light)

            # Glowing Tensor Core 3x3 array inside SoC
            grid_n = 3
            cell_size = core_size / grid_n
            for gx in range(grid_n):
                for gy in range(grid_n):
                    bx = cx - core_size / 2 + (gx + 0.5) * cell_size
                    by = cy - core_size / 2 + (gy + 0.5) * cell_size
                    b_half = cell_size * 0.35
                    block = [
                        (bx - b_half, by - b_half), (bx + b_half, by - b_half),
                        (bx + b_half, by + b_half), (bx - b_half, by + b_half)
                    ]
                    lines(sc, [block + [block[0]]], 1.5 * s, 0.7, chip_light)
                    # Center neural node
                    polys(sc, [[(bx - b_half * 0.4, by - b_half * 0.4), (bx + b_half * 0.4, by - b_half * 0.4),
                                (bx + b_half * 0.4, by + b_half * 0.4), (bx - b_half * 0.4, by + b_half * 0.4)]], 0.9, chip_light)

            # Precision status LED array on top and bottom border of the die
            led_n = 10
            for li in range(led_n):
                lx = cx - cw / 2 + bevel * 2 + (li + 0.5) * (cw - bevel * 4) / led_n
                ly_top = cy - ch / 2 + bevel * 1.8
                ly_bot = cy + ch / 2 - bevel * 1.8
                lr = sc.px(2.5)
                ang = np.linspace(0, 2 * np.pi, 10)
                polys(sc, [[(lx + lr * np.cos(a), ly_top + lr * np.sin(a)) for a in ang]], 1.0, chip_light)
                polys(sc, [[(lx + lr * np.cos(a), ly_bot + lr * np.sin(a)) for a in ang]], 0.8, chip_light)

            # Glowing optical bus interconnects radiating outward from the neural die to package edge
            bus_lanes = []
            for side_i in range(4):
                for bl in [-0.25, 0.0, 0.25]:
                    if side_i == 0:  # right
                        bus_lanes.append([(cx + core_size / 2, cy + bl * core_size), (cx + cw / 2 - bevel, cy + bl * core_size)])
                    elif side_i == 1:  # bottom
                        bus_lanes.append([(cx + bl * core_size, cy + core_size / 2), (cx + bl * core_size, cy + ch / 2 - bevel)])
                    elif side_i == 2:  # left
                        bus_lanes.append([(cx - core_size / 2, cy + bl * core_size), (cx - cw / 2 + bevel, cy + bl * core_size)])
                    else:  # top
                        bus_lanes.append([(cx + bl * core_size, cy - core_size / 2), (cx + bl * core_size, cy - ch / 2 + bevel)])
            lines(sc, bus_lanes, 1.8 * s, 0.95, chip_light)

            # Micro-decoupling capacitors ringing the SoC perimeter (tiny 0402 SMD packages)
            cap_w, cap_h = sc.px(8), sc.px(14)
            for side_i in range(4):
                n_caps = 8
                for ci in range(n_caps):
                    frac = (ci + 0.5) / n_caps
                    if side_i == 0:  # right
                        c_px = cx + cw / 2 + sc.px(22)
                        c_py = cy - ch / 2 + frac * ch
                    elif side_i == 1:  # bottom
                        c_px = cx - cw / 2 + frac * cw
                        c_py = cy + ch / 2 + sc.px(22)
                    elif side_i == 2:  # left
                        c_px = cx - cw / 2 - sc.px(22)
                        c_py = cy - ch / 2 + frac * ch
                    else:  # top
                        c_px = cx - cw / 2 + frac * cw
                        c_py = cy - ch / 2 - sc.px(22)

                    # Ceramic cap body with solder terminals
                    c_rect = [
                        (c_px - cap_w / 2, c_py - cap_h / 2), (c_px + cap_w / 2, c_py - cap_h / 2),
                        (c_px + cap_w / 2, c_py + cap_h / 2), (c_px - cap_w / 2, c_py + cap_h / 2)
                    ]
                    polys(sc, [c_rect], 1.0, solder_pads)
                    sc.base += polys(sc, [c_rect])[..., None] * np.array([0.15, 0.14, 0.11], dtype=np.float32)
        else:
            # Memory / Co-processor: sleek circuit traces and activity status line
            diag_line = [
                (cx - cw / 2 + bevel * 2, cy - ch / 2 + bevel * 2),
                (cx + cw / 2 - bevel * 2, cy - ch / 2 + bevel * 2)
            ]
            lines(sc, [diag_line], 2.2 * s, 0.85, chip_light)
            bot_line = [
                (cx - cw / 2 + bevel * 2, cy + ch / 2 - bevel * 2),
                (cx + cw / 2 - bevel * 2, cy + ch / 2 - bevel * 2)
            ]
            lines(sc, [bot_line], 1.8 * s, 0.7, chip_light)
            # Pin 1 indicator dot
            dot_r = sc.px(4.0)
            dot_pts = [(cx - cw / 2 + bevel * 2.2 + dot_r * np.cos(a), cy - ch / 2 + bevel * 2.2 + dot_r * np.sin(a))
                       for a in np.linspace(0, 2 * np.pi, 12)]
            polys(sc, [dot_pts], 1.0, chip_light)

    # 7. Aura Lighting Layer Assembly
    # Core lit traces (crisp hot center)
    sc.light += copper_lit * 0.9 + chip_light * 1.0
    # Add multi-tier neon glow
    sc.light += glow(copper_lit, s, tight=1.2, wide=0.7) * 0.85
    sc.light += glow(chip_light, s, tight=1.4, wide=0.9) * 1.1

    # Soft ambient fiber optic glow spreading across the substrate
    sc.light += blur(copper_lit + chip_light, 60 * s) * 0.35

    # Base layer ambient illumination around active components
    sc.base += blur(sc.light, 40 * s)[..., None] * np.array([0.03, 0.08, 0.07], dtype=np.float32)
    sc.base += grain(sc, 0.005)
