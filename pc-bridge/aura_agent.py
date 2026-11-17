"""Aura Phone Sync - PC agent.

Runs in the background and keeps the phone's Aura wallpaper up to date. Nothing streams
continuously; the agent only sends something when it changes:
  * wallpaper changed -> builds a phone version + light map, sends it once
  * lighting effect changed -> records one loop of the effect (e.g. one rainbow cycle), sends it once
The phone plays the loop on its own, with or without a connection.

Links (both carry the same encrypted messages):
  * internet: public MQTT relays over TLS, messages retained so the phone catches up whenever it connects
  * USB: TCP 127.0.0.1:47801 through `adb reverse`; also how the phone gets paired the first time

Run:  python aura_agent.py      (pythonw aura_agent.py runs it without a window)
"""
import base64, hashlib, json, os, shutil, socket, struct, subprocess, sys, threading, time
import numpy as np
from PIL import Image
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import capture, mqtt_lite, wallpaper_assets

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "agent_state")
TCP_PORT = 47801
FPS = 10
RECORD_SECONDS = 30
MIN_RERECORD_GAP = 120   # seconds; stops unsteady effects (music, games) from re-sending constantly
CHUNK = 48_000            # one relay rejects retained messages above ~64 KB
CHECK_EVERY = 2.0         # seconds between "is the effect still the same?" checks


def log(*a):
    line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    with open(os.path.join(STATE, "agent.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- pairing + crypto

def load_pair():
    path = os.path.join(STATE, "pair.json")
    if os.path.exists(path):
        return json.load(open(path))
    pair = {"id": os.urandom(8).hex(), "key": base64.b64encode(AESGCM.generate_key(256)).decode()}
    json.dump(pair, open(path, "w"))
    return pair


class Sealer:
    def __init__(self, key_b64):
        self.aes = AESGCM(base64.b64decode(key_b64))

    def seal(self, name, data):
        nonce = os.urandom(12)
        return nonce + self.aes.encrypt(nonce, data, name.encode())

    def open(self, name, blob):
        return self.aes.decrypt(blob[:12], blob[12:], name.encode())


# ---------------------------------------------------------------- links

class Links:
    """Keeps the latest state ("retained" messages) and delivers it over every link."""

    def __init__(self, pair):
        self.pair = pair
        self.base = f"aps/{pair['id']}"
        self.sealer = Sealer(pair["key"])
        self.retained = {}                     # name -> sealed payload, in publish order
        self.lock = threading.Lock()
        self.brokers = {}                      # host -> MqttClient
        self.usb = []
        for host, port in mqtt_lite.BROKERS:
            threading.Thread(target=self._broker_loop, args=(host, port), daemon=True).start()
        threading.Thread(target=self._usb_server, daemon=True).start()
        threading.Thread(target=self._adb_reverse_loop, daemon=True).start()

    def set(self, items, drop_prefix=None):
        """items: [(name, bytes)]. Replaces retained state and pushes it to every link."""
        sealed = [(n, self.sealer.seal(n, d)) for n, d in items]
        with self.lock:
            if drop_prefix:
                for k in [k for k in self.retained if k.startswith(drop_prefix)]:
                    del self.retained[k]
            for n, s in sealed:
                self.retained.pop(n, None)
                self.retained[n] = s
        for n, s in sealed:
            self._push(n, s)

    def _push(self, name, sealed):
        for host, c in list(self.brokers.items()):
            try:
                c.publish(f"{self.base}/{name}", sealed, retain=True)
            except Exception:
                c.alive = False
        for conn in self.usb[:]:
            self._usb_send(conn, name, sealed)

    def _snapshot(self):
        with self.lock:
            return list(self.retained.items())

    # -- internet relays
    def _broker_loop(self, host, port):
        delay = 5
        while True:
            client = mqtt_lite.MqttClient(host, port, on_message=lambda t, p, h=host: self._on_relay(h, t, p))
            try:
                client.connect()
                client.subscribe(f"{self.base}/hello")
                self.brokers[host] = client
                log(f"[relay] connected {host}")
                for n, s in self._snapshot():
                    client.publish(f"{self.base}/{n}", s, retain=True)
                delay = 5
                while client.alive:
                    time.sleep(2)
            except Exception as e:
                log(f"[relay] {host} unavailable: {e}")
            self.brokers.pop(host, None)
            client.close()
            time.sleep(delay)
            delay = min(delay * 2, 300)

    def _on_relay(self, host, topic, payload):
        if not topic.endswith("/hello") or not payload:
            return
        try:
            hello = json.loads(self.sealer.open("hello", payload))
        except Exception:
            return
        self._answer_hello(hello, lambda n, s: self.brokers[host].publish(f"{self.base}/{n}", s, retain=True), host)

    def _answer_hello(self, hello, send, via):
        snap = dict(self._snapshot())
        missing = []
        info = snap.get("wp/info")
        if info and hello.get("wp") != json.loads(self.sealer.open("wp/info", info))["hash"]:
            missing += [n for n in snap if n.startswith("wp/")]
        fx = snap.get("fx")
        if fx and hello.get("fx") != self._fx_hash(fx):
            missing += ["fx", "fx/info"]
        log(f"[{via}] phone checked in; sending {len(missing)} update(s)")
        for n in missing:
            send(n, snap[n])

    def _fx_hash(self, sealed):
        data = self.sealer.open("fx", sealed)
        hlen = struct.unpack(">I", data[:4])[0]
        return json.loads(data[4:4 + hlen])["hash"]

    # -- USB
    def _usb_server(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", TCP_PORT))
        srv.listen(4)
        while True:
            conn, _ = srv.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=self._usb_client, args=(conn,), daemon=True).start()

    def _usb_client(self, conn):
        log("[usb] phone connected; pairing")
        self._usb_send(conn, "pair", json.dumps(self.pair).encode())
        self.usb.append(conn)
        try:
            f = conn.makefile("rb")
            while True:
                n = struct.unpack(">H", f.read(2))[0]
                name = f.read(n).decode()
                ln = struct.unpack(">I", f.read(4))[0]
                payload = f.read(ln)
                if name == "hello":
                    hello = json.loads(self.sealer.open("hello", payload))
                    self._answer_hello(hello, lambda nm, s: self._usb_send(conn, nm, s), "usb")
        except Exception:
            pass
        if conn in self.usb:
            self.usb.remove(conn)
        log("[usb] phone disconnected")

    def _usb_send(self, conn, name, payload):
        nb = name.encode()
        try:
            conn.sendall(struct.pack(">H", len(nb)) + nb + struct.pack(">I", len(payload)) + payload)
        except OSError:
            if conn in self.usb:
                self.usb.remove(conn)

    def _adb_reverse_loop(self):
        adb = shutil.which("adb") or r"C:\Android\Sdk\platform-tools\adb.exe"
        if not os.path.exists(adb):
            return
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        while True:
            try:
                out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10,
                                     creationflags=flags).stdout
                for line in out.splitlines()[1:]:
                    if line.strip().endswith("device"):
                        subprocess.run([adb, "-s", line.split()[0], "reverse", f"tcp:{TCP_PORT}", f"tcp:{TCP_PORT}"],
                                       capture_output=True, timeout=10, creationflags=flags)
            except Exception:
                pass
            time.sleep(5)


# ---------------------------------------------------------------- effect loop

def record(cap, ext, seconds):
    """Samples the grid at FPS for `seconds`; also learns which pixels change color (= lights)."""
    frames, s1, s2, n, rgb = [], None, None, 0, None
    t_next = time.perf_counter()
    for _ in range(int(seconds * FPS)):
        rgb = cap.grab()
        if rgb is None:
            return None, None, None
        g = ext.extract(rgb)
        if g is None:
            return None, None, None
        frames.append(g)
        small = rgb[::4, ::4].astype(np.float32)
        ch = np.stack([small[..., 0] - small[..., 1], small[..., 1] - small[..., 2]], -1)
        s1 = ch if s1 is None else s1 + ch
        s2 = ch * ch if s2 is None else s2 + ch * ch
        n += 1
        t_next += 1.0 / FPS
        time.sleep(max(0.0, t_next - time.perf_counter()))
    std = np.sqrt(np.maximum(s2 / n - (s1 / n) ** 2, 0)).max(-1)
    moving = np.clip((std - 10) / 20, 0, 1)
    return np.stack(frames), moving, rgb.copy()


def tint_mask(rgb, base_path):
    """0..1 at 480x270: where the live wallpaper's color differs from the untinted base image.
    Desktop icons also differ, but they add sharp edges the base doesn't have, so those are dropped."""
    from PIL import ImageFilter
    W, H = 480, 270
    c = np.asarray(Image.fromarray(np.ascontiguousarray(rgb)).resize((W, H), Image.BOX)).astype(np.float32)
    b = np.asarray(Image.open(base_path).convert("RGB").resize((W, H), Image.BOX)).astype(np.float32)
    t = c - b
    chroma = np.sqrt(((t - t.mean(axis=2, keepdims=True)) ** 2).sum(2))
    chroma = np.asarray(Image.fromarray(np.clip(chroma * 4, 0, 255).astype(np.uint8))
                        .filter(ImageFilter.GaussianBlur(3))).astype(np.float32) / 4
    edges = lambda a: np.asarray(Image.fromarray(np.clip(a.mean(2), 0, 255).astype(np.uint8))
                                 .filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    e = np.abs(edges(c) - edges(b))
    e = np.asarray(Image.fromarray(np.clip(e, 0, 255).astype(np.uint8))
                   .filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(4))).astype(np.float32)
    return np.clip((chroma - 6) / 20, 0, 1) * np.clip(1 - (e - 15) / 25, 0, 1)


def analyze(frames):
    """Reduces a recording to the shortest loop that reproduces it."""
    f = frames.astype(np.float32)
    if np.abs(f - f.mean(0)).mean(axis=(1, 2, 3)).max() < 10:
        return f.mean(0, keepdims=True).astype(np.uint8), "steady"
    N = len(f)
    lags = list(range(int(0.6 * FPS), N // 2 + 1))
    d = {L: np.abs(f[L:] - f[:-L]).mean() for L in lags}
    dmin = min(d.values())
    peak = 0.0
    for L in lags:
        # a real period: the pattern drifted away and then came back to where it started
        if d[L] < 14 and d[L] <= dmin * 1.15 + 1.5 and d[L] < 0.35 * peak:
            return frames[N - L:], f"{L / FPS:.1f}s loop"
        peak = max(peak, d[L])
    # No repeat found (very slow or audio-reactive): keep the last 20 s and blend the seam over 3 s.
    clip = f[-20 * FPS:].copy()
    k = 3 * FPS
    w = np.linspace(0, 1, k)[:, None, None, None]
    clip[-k:] = clip[-k:] * (1 - w) + clip[:k] * w
    return clip.astype(np.uint8), "20s free-form"


def fx_payload(loop):
    h = hashlib.sha1(loop.tobytes()).hexdigest()[:16]
    head = json.dumps({"fps": FPS, "n": len(loop), "w": capture.GRID_W, "h": capture.GRID_H, "hash": h}).encode()
    return struct.pack(">I", len(head)) + head + loop.tobytes(), h


def distance_to_loop(g, loop):
    return min(np.abs(g.astype(np.float32) - fr.astype(np.float32)).mean() for fr in loop)


# ---------------------------------------------------------------- main

class Agent:
    def __init__(self):
        os.makedirs(STATE, exist_ok=True)
        self.pair = load_pair()
        self.links = Links(self.pair)
        self.wp_key = None
        self.wp_path = None
        self.pc_mask = None
        self.cap = None
        self.ext = None
        self.loop = None
        self.fx_hash = None
        self.need_record = True
        self.misses = 0
        self.last_record = 0.0

    def learned_path(self):
        return os.path.join(STATE, "learned_" + hashlib.sha1(self.wp_key.encode()).hexdigest()[:12] + ".png")

    def publish_wallpaper(self):
        lp = self.learned_path()
        learned = np.asarray(Image.open(lp)).astype(np.float32) / 255.0 if os.path.exists(lp) else None
        blob, h, self.pc_mask = wallpaper_assets.build(self.wp_path, learned)
        chunks = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)]
        info = json.dumps({"hash": h, "chunks": len(chunks), "size": len(blob)}).encode()
        items = [(f"wp/{i}", c) for i, c in enumerate(chunks)] + [("wp/info", info)]
        self.links.set(items, drop_prefix="wp/")
        self.ext = None
        self.need_record = True
        log(f"[wallpaper] {os.path.basename(os.path.dirname(self.wp_path)) or self.wp_path}: "
            f"sent {len(blob) // 1024} KB ({'learned' if learned is not None else 'detected'} lights), id {h}")

    def check_wallpaper(self):
        try:
            path = wallpaper_assets.current_wallpaper()
            st = os.stat(path)
        except Exception:
            return
        key = f"{path}|{st.st_mtime_ns}|{st.st_size}"
        if key != self.wp_key:
            self.wp_key, self.wp_path = key, path
            self.publish_wallpaper()

    def step(self):
        self.check_wallpaper()
        if self.pc_mask is None:
            return
        if self.cap is None:
            hwnd = capture.find_wallpaper_window()
            if not hwnd:
                return
            self.cap = capture.Capturer(hwnd)
            self.ext = None
        if self.ext is None:
            self.ext = capture.GridExtractor(self.cap.w, self.cap.h, self.pc_mask)

        if self.need_record:
            self.last_record = time.time()
            frames, moving, last = record(self.cap, self.ext, RECORD_SECONDS)
            if frames is None:
                return self.reset_capture()
            if self.learn(moving, last):
                return
            loop, kind = analyze(frames)
            payload, h = fx_payload(loop)
            self.loop, self.need_record, self.misses = loop, False, 0
            if h != self.fx_hash:
                self.fx_hash = h
                self.links.set([("fx", payload), ("fx/info", json.dumps({"hash": h}).encode())])
                log(f"[effect] new lighting: {kind}, {len(payload) // 1024 + 1} KB sent")
            return

        rgb = self.cap.grab()
        g = self.ext.extract(rgb) if rgb is not None else None
        if g is None:
            return self.reset_capture()
        self.misses = self.misses + 1 if distance_to_loop(g, self.loop) > 20 else 0
        if self.misses >= 2 and time.time() - self.last_record > MIN_RERECORD_GAP:
            log("[effect] lighting changed on the PC; recording it")
            self.need_record = True

    def learn(self, moving, last_rgb):
        """Grows this wallpaper's map of Aura-lit areas; re-sends the wallpaper when it grew a lot."""
        new = np.maximum(moving, tint_mask(last_rgb, self.wp_path))
        new[(new > 0) & (new < 0.2)] = 0
        if not 0.0002 < (new > 0.5).mean() < 0.85:
            return False
        lp = self.learned_path()
        old = np.asarray(Image.open(lp)).astype(np.float32) / 255.0 if os.path.exists(lp) else np.zeros_like(new)
        merged = np.maximum(old, new)
        grown = ((merged > 0.5) & (old <= 0.5)).mean()
        if grown < 0.01:
            return False
        Image.fromarray((merged * 255).astype(np.uint8)).save(lp)
        log(f"[wallpaper] learned more Aura-lit area (+{grown * 100:.1f}% of screen, "
            f"{(merged > 0.5).mean() * 100:.0f}% total)")
        self.publish_wallpaper()
        return True

    def reset_capture(self):
        if self.cap:
            self.cap.close()
        self.cap = self.ext = None

    def run(self):
        log(f"Aura Phone Sync agent started (pair id {self.pair['id']})")
        while True:
            try:
                self.step()
            except Exception as e:
                log("[error]", repr(e))
                self.reset_capture()
            time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    if "--no-usb" in sys.argv:          # internet only (for testing the relay path)
        Links._usb_server = Links._adb_reverse_loop = lambda self: None
    if sys.executable.lower().endswith("pythonw.exe"):
        sys.stdout = open(os.devnull, "w")
    Agent().run()
