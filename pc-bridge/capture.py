"""Reads the live Aura wallpaper window and samples a 16x9 grid of light colors."""
import ctypes, ctypes.wintypes as wt
import numpy as np
from PIL import Image

GRID_W, GRID_H = 16, 9

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.SetProcessDPIAware()
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_wallpaper_window():
    """The top-level 'Aura Wallpaper Service' window that hosts the WebView renderer."""
    found = []

    def check(h, _):
        title = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, title, 256)
        user32.GetClassNameW(h, cls, 256)
        if title.value == "Aura Wallpaper Service" and cls.value.startswith("HwndWrapper[Aura Wallpaper Service.exe") \
                and user32.IsWindowVisible(h):
            found.append(h)
        return True

    check_cb = WNDENUMPROC(check)

    def top(h, _):
        check(h, 0)
        user32.EnumChildWindows(h, check_cb, 0)  # the wallpaper is re-parented under the desktop
        return True

    user32.EnumWindows(WNDENUMPROC(top), 0)
    return found[0] if found else None


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class Capturer:
    """PrintWindow into a DIB section; works while the desktop is covered by other windows."""

    def __init__(self, hwnd):
        self.hwnd = hwnd
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        self.w, self.h = r.right - r.left, r.bottom - r.top
        bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), self.w, -self.h, 1, 32, 0, 0, 0, 0, 0, 0)
        self.dc = gdi32.CreateCompatibleDC(None)
        bits = ctypes.c_void_p()
        self.bmp = gdi32.CreateDIBSection(self.dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        gdi32.SelectObject(self.dc, self.bmp)
        buf = (ctypes.c_ubyte * (self.w * self.h * 4)).from_address(bits.value)
        self.pixels = np.frombuffer(buf, dtype=np.uint8).reshape(self.h, self.w, 4)

    def grab(self):
        if not user32.PrintWindow(self.hwnd, self.dc, 2):
            return None
        return self.pixels[..., 2::-1]  # BGRA -> RGB view

    def close(self):
        gdi32.DeleteObject(self.bmp)
        gdi32.DeleteDC(self.dc)


class GridExtractor:
    """Averages the brightest light-mask pixels in each grid cell of the captured frame."""

    def __init__(self, w, h, mask_img):
        mask = mask_img.convert("L").resize((w, h), Image.BILINEAR)
        m = np.asarray(mask).astype(np.float32) / 255.0
        self.cells = []
        for gy in range(GRID_H):
            for gx in range(GRID_W):
                x0, x1 = gx * w // GRID_W, (gx + 1) * w // GRID_W
                y0, y1 = gy * h // GRID_H, (gy + 1) * h // GRID_H
                ys, xs = np.nonzero(m[y0:y1, x0:x1] > 0.25)
                self.cells.append((ys + y0, xs + x0) if len(ys) >= 6 else None)
        self.ref = 140.0  # running brightness reference, so dim breathing phases stay dim

    def extract(self, rgb):
        grid = np.full((GRID_H * GRID_W, 3), np.nan, np.float32)
        for i, idx in enumerate(self.cells):
            if idx is None:
                continue
            px = rgb[idx].astype(np.float32)
            v = px.max(axis=1)
            score = (v - px.min(axis=1)) * v  # saturated AND bright = an LED, not haze or highlights
            top = px[score >= np.percentile(score, 75)]
            grid[i] = top.mean(axis=0)
        known = ~np.isnan(grid[:, 0])
        if not known.any():
            return None
        peak = np.nanmax(grid)
        self.ref = max(peak, self.ref * 0.995, 60.0)
        grid = fill_unknown(grid.reshape(GRID_H, GRID_W, 3))
        return vivid(grid, self.ref)


def fill_unknown(g):
    """Cells with no lights take the color of the nearest cell that has one."""
    known = np.argwhere(~np.isnan(g[..., 0]))
    out = g.copy()
    for y in range(GRID_H):
        for x in range(GRID_W):
            if np.isnan(g[y, x, 0]):
                ky, kx = known[np.argmin((known[:, 0] - y) ** 2 + (known[:, 1] - x) ** 2)]
                out[y, x] = g[ky, kx]
    return out


def vivid(g, ref):
    """Rescale to full brightness and push saturation, so the phone gets clean LED-like colors."""
    level = np.clip(g.max(axis=2, keepdims=True) / ref, 0, 1)
    mx = np.maximum(g.max(axis=2, keepdims=True), 1)
    mn = g.min(axis=2, keepdims=True)
    norm = g / mx                                # hue at full value
    sat = np.clip((mx - mn) / mx * 1.35, 0, 1)   # mildly boosted saturation
    color = 1 - (1 - norm) / np.maximum((mx - mn) / mx, 1e-3) * sat
    color = np.clip(color, 0, 1) * level
    return (color * 255).astype(np.uint8)
