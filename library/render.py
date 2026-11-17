"""Renders wallpaper designs into AuraSync packs.

  python render.py                     all designs, full resolution
  python render.py neon_horizon --draft  one design at half resolution, for quick review
"""
import importlib, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "designs"))
import numpy as np
from toolkit import Scene, PHONE, PHONE_LAND, PC, save_pack

HERE = os.path.dirname(os.path.abspath(__file__))


def render(name, draft=False):
    """Phone-first rendering: generates native portrait and landscape scenes."""
    mod = importlib.import_module(name)
    f = 0.5 if draft else 1.0
    seed = sum(map(ord, name))

    # 1. Native Phone Portrait (1080x2408)
    sc_port = Scene(int(PHONE[0] * f), int(PHONE[1] * f), seed=seed)
    mod.draw(sc_port)

    # 2. Native Phone Landscape (2408x1080)
    sc_land = Scene(int(PHONE_LAND[0] * f), int(PHONE_LAND[1] * f), seed=seed)
    mod.draw(sc_land)

    out = os.path.join(HERE, "packs" if not draft else "drafts", name)
    save_pack(out, mod.NAME, mod.DESC, "AuraSync original", sc_port, sc_land, mod.COLOR)
    return out


def write_index():
    """packs/library.json: the catalogue the gallery and the apps read."""
    import json
    packs = []
    for d in sorted(os.listdir(os.path.join(HERE, "packs"))):
        m = os.path.join(HERE, "packs", d, "meta.json")
        if os.path.exists(m):
            packs.append(json.load(open(m)))
    json.dump({"packs": packs}, open(os.path.join(HERE, "packs", "library.json"), "w"), indent=1)
    return len(packs)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    draft = "--draft" in sys.argv
    names = args or sorted(f[:-3] for f in os.listdir(os.path.join(HERE, "designs")) if f.endswith(".py"))
    for n in names:
        t = time.time()
        out = render(n, draft)
        print(f"{n}: {time.time() - t:.1f}s -> {out}")
    if not draft:
        print("library.json:", write_index(), "packs")
