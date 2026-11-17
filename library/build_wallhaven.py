"""Turns the downloaded Wallhaven images (wh_cache/src) into AuraSync packs."""
import os, sys, glob
import cv2, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import builder_anime as B

HERE = os.path.dirname(os.path.abspath(__file__))
# id, pack id, name, description, aura colour, light-map kind
LIST = [
 ("y8lqo7", "astro_nebula", "Astronaut Nebula", "A helmet full of galaxy; the nebula and visor glow.", "#00e5ff", "neon"),
 ("kx5v57", "arcade_den", "Arcade Den", "A neon-lit gamer room, every sign alive.", "#ff2fb4", "neon"),
 ("ex136k", "midnight_konbini", "Midnight Konbini", "A quiet Tokyo street, signs buzzing in the dark.", "#ff6a00", "neon"),
 ("lmd95y", "mega_city", "Mega City", "A cyberpunk city seen from above.", "#00e5ff", "neon"),
 ("kxj3l1", "synth_peaks", "Synth Peaks", "Retro-wave mountains under a violet sky.", "#ff2fb4", "neon"),
 ("y86g17", "neon_circuit", "Neon Circuit", "Glowing circuit lanes cutting through a cube.", "#ff6a00", "neon"),
 ("72yzje", "glow_shore", "Glow Shore", "A bioluminescent beach at night.", "#00e5ff", "neon"),
 ("rdm6km", "orbit_window", "Orbit Window", "A bedroom with a view of the planet.", "#3d7bff", "neon"),
 ("e76ge8", "ring_of_fire", "Ring of Fire", "A golden ring burning above a lone knight.", "#ffd400", "general"),
 ("k81776", "pink_planet", "Pink Planet", "A magenta world rising over a lone walker.", "#ff2fb4", "neon"),
 ("839zjk", "neon_portal", "Neon Portal", "A glowing ring in a dark cave, reflected below.", "#ff2fb4", "neon"),
 ("83lq62", "prism_cube", "Prism Cube", "A glass cube refracting colour.", "#7a5cff", "general"),
 ("136m9w", "red_alley", "Red Alley", "Lit houses and lanterns in a red night.", "#ff3b3b", "neon"),
 ("mdmp38", "cyber_eye", "Cyber Eye", "A visor full of neon reflections.", "#00e5ff", "neon"),
 ("qzdqvr", "deep_shark", "Deep Shark", "A shark with glowing green stripes.", "#2bff88", "neon"),
]

def focal_x(img):
    small = cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA)
    _, light = B.extract_light_map(small, "neon")
    prof = cv2.GaussianBlur(light.sum(0).reshape(1, -1), (0, 0), 25).ravel()
    w = 0.22  # portrait window is ~21% of the width: find the window with the most light
    k = int(480 * w)
    c = np.convolve(prof, np.ones(k), "valid")
    return float((c.argmax() + k / 2) / 480)

for wid, pid, name, desc, col, kind in LIST:
    src = glob.glob(os.path.join(HERE, "wh_cache", "src", wid + ".*"))[0]
    img = cv2.cvtColor(cv2.imread(src), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    fx = focal_x(img)
    B.build_pack_from_images(pid, name, desc, col, src, None, land_focal=(0.5, 0.5), port_focal=(fx, 0.5), kind=kind)
    print(pid, "portrait focal", round(fx, 2))
