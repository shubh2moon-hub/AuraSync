"""Search Wallhaven for new wallpaper packs and download them."""
import urllib.request, json, urllib.parse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMP = os.path.join(ROOT, "temp_wallpapers")
os.makedirs(TEMP, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def search(q, cat='011'):
    url = f'https://wallhaven.cc/api/v1/search?q={urllib.parse.quote(q)}&categories={cat}&purity=100&sorting=favorites&atleast=2560x1440'
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read()).get('data', [])
            return [(d['id'], d['path'], d.get('resolution',''), d.get('favorites',0)) for d in data[:8]]
    except Exception as e:
        return [('ERR', str(e), '', 0)]

def download(url, out_path):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            with open(out_path, 'wb') as f:
                f.write(r.read())
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

queries = [
    ('naruto rasengan chakra', 'naruto'),
    ('chainsaw man denji power', 'chainsaw_man'),
    ('one piece luffy gear 5', 'one_piece'),
    ('neon evangelion unit 01', 'evangelion'),
    ('blade runner 2049 cinematic', 'blade_runner'),
]

for q, name in queries:
    results = search(q)
    print(f'== {q} ==')
    for r in results[:3]:
        print(f'  {r[0]}: {r[2]} fav={r[3]} -> {r[1]}')
    # Download top result
    if results and results[0][0] != 'ERR':
        top = results[0]
        ext = os.path.splitext(top[1])[1] or '.jpg'
        out = os.path.join(TEMP, f'{name}{ext}')
        print(f'  Downloading top: {top[1]}')
        ok = download(top[1], out)
        if ok:
            print(f'  Saved -> {out}')
    print()
