// The AuraSync window: the same layout as the phone app (wallpapers, lighting, phone), drawn with plain GDI.
// It only exists while open. Closing it frees every bitmap, font and buffer; the wallpaper keeps running.
// Included by main.cpp after the state and OnCommand it drives.

namespace ui {

struct Hit { RECT r; int id; };
static Hit g_hits[200];
static int g_nHits, g_scroll, g_contentH, g_scale = 100, g_hover = -1;
static HFONT g_fNormal, g_fBold, g_fTitle, g_fSmall;
static HBITMAP g_thumbs[64];
static HBITMAP g_back;
static int g_backW, g_backH;

enum { ID_CHOOSE_HERE = ID_FOLLOW + 1, ID_OPEN = 1504 };

static const COLORREF BG = RGB(11, 12, 16), PANEL = RGB(20, 22, 28), LINE = RGB(38, 42, 51),
                      TEXT = RGB(232, 234, 239), MUTED = RGB(139, 146, 161), SEL = RGB(42, 47, 59), SELLINE = RGB(232, 234, 239);

static int Sc(int v) { return MulDiv(v, g_scale, 100); }

static void Fill(HDC dc, const RECT& r, COLORREF c) {
    HBRUSH b = CreateSolidBrush(c); FillRect(dc, &r, b); DeleteObject(b);
}

static void Box(HDC dc, const RECT& r, COLORREF fill, COLORREF line, int radius) {
    HBRUSH b = CreateSolidBrush(fill); HPEN p = CreatePen(PS_SOLID, 1, line);
    HGDIOBJ ob = SelectObject(dc, b), op = SelectObject(dc, p);
    RoundRect(dc, r.left, r.top, r.right, r.bottom, radius, radius);
    SelectObject(dc, ob); SelectObject(dc, op); DeleteObject(b); DeleteObject(p);
}

static void Text(HDC dc, const wchar_t* s, int x, int y, HFONT f, COLORREF c) {
    SelectObject(dc, f); SetTextColor(dc, c);
    TextOutW(dc, x, y, s, rt::Len(s));
}

static int TextW(HDC dc, const wchar_t* s, HFONT f) {
    SIZE sz; SelectObject(dc, f); GetTextExtentPoint32W(dc, s, rt::Len(s), &sz); return sz.cx;
}

static void AddHit(int x0, int y0, int x1, int y1, int id) {
    if (g_nHits < 200) { g_hits[g_nHits].r = { x0, y0, x1, y1 }; g_hits[g_nHits].id = id; ++g_nHits; }
}

// A wallpaper preview, decoded only when its card first scrolls into view.
static HBITMAP LoadThumb(int i, int w, int h) {
    if (g_thumbs[i]) return g_thumbs[i];
    wchar_t path[MAX_PATH]; rt::Path(path, g_packsDir, g_packs[i].id, L"pc_preview.jpg");
    IWICImagingFactory* wic = nullptr;
    if (FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wic)))) return nullptr;
    IWICBitmapDecoder* dec = nullptr; IWICBitmapFrameDecode* fr = nullptr;
    IWICBitmapScaler* sc = nullptr; IWICFormatConverter* cv = nullptr;
    HBITMAP bmp = nullptr;
    if (SUCCEEDED(wic->CreateDecoderFromFilename(path, nullptr, GENERIC_READ, WICDecodeMetadataCacheOnDemand, &dec)) &&
        SUCCEEDED(dec->GetFrame(0, &fr)) && SUCCEEDED(wic->CreateBitmapScaler(&sc)) &&
        SUCCEEDED(sc->Initialize(fr, w, h, WICBitmapInterpolationModeFant)) && SUCCEEDED(wic->CreateFormatConverter(&cv)) &&
        SUCCEEDED(cv->Initialize(sc, GUID_WICPixelFormat32bppBGR, WICBitmapDitherTypeNone, nullptr, 0, WICBitmapPaletteTypeCustom))) {
        BITMAPINFO bi = {};
        bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER); bi.bmiHeader.biWidth = w; bi.bmiHeader.biHeight = -h;
        bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 32; bi.bmiHeader.biCompression = BI_RGB;
        void* bits = nullptr;
        bmp = CreateDIBSection(nullptr, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
        if (bmp && FAILED(cv->CopyPixels(nullptr, w * 4, w * 4 * h, (BYTE*)bits))) { DeleteObject(bmp); bmp = nullptr; }
    }
    Release(cv); Release(sc); Release(fr); Release(dec); Release(wic);
    g_thumbs[i] = bmp;
    return bmp;
}

static void Section(HDC dc, const wchar_t* title, int x, int& y, int H) {
    y += Sc(26);
    Text(dc, title, x, y - g_scroll, g_fSmall, MUTED);
    y += Sc(24);
    (void)H;
}

// Draws a chip at the cursor, wrapping to the next row when it would overflow.
static void Chip(HDC dc, const wchar_t* label, int& x, int& y, int left, int right, bool selected, bool dim, int id, int H) {
    int pad = Sc(16), h = Sc(34);
    int w = TextW(dc, label, g_fNormal) + pad * 2;
    if (x + w > right) { x = left; y += h + Sc(8); }
    int yy = y - g_scroll;
    if (yy + h > 0 && yy < H) {
        RECT r = { x, yy, x + w, yy + h };
        Box(dc, r, selected ? SEL : PANEL, selected ? SELLINE : LINE, Sc(10));
        SetBkMode(dc, TRANSPARENT);
        Text(dc, label, x + pad, yy + (h - Sc(18)) / 2 - Sc(1), g_fNormal, dim ? MUTED : TEXT);
        AddHit(r.left, r.top, r.right, r.bottom, id);
    }
    x += w + Sc(8);
}

static void Paint(HDC dc, int W, int H) {
    RECT all = { 0, 0, W, H };
    Fill(dc, all, BG);
    SetBkMode(dc, TRANSPARENT);
    g_nHits = 0;
    int left = Sc(24), right = W - Sc(24), y = Sc(20);
    bool ghActive = g_set.followGHelper && g_ghFound;

    Text(dc, L"AuraSync", left, y - g_scroll, g_fTitle, TEXT);
    y += Sc(40);
    {
        wchar_t st[160];
        rt::Copy(st, link::Paired() ? L"Phone connected \x2013 it follows this PC." : L"Phone not connected yet. Pair it below.", 160);
        wchar_t n[8]; rt::IntToStr(n, link::RelaysUp());
        rt::Cat(st, L"   Relays up: ", 160); rt::Cat(st, n, 160); rt::Cat(st, L" of 3", 160);
        Text(dc, st, left, y - g_scroll, g_fNormal, MUTED);
        y += Sc(26);
    }

    // ---- wallpapers
    Section(dc, L"WALLPAPER", left, y, H);
    int tw = Sc(168), th = Sc(94), cardW = tw + Sc(12), cardH = th + Sc(48), gap = Sc(10);
    int perRow = (right - left + gap) / (cardW + gap); if (perRow < 1) perRow = 1;
    for (int i = 0; i < g_packCount; ++i) {
        int col = i % perRow, row = i / perRow;
        int x = left + col * (cardW + gap), yy = y + row * (cardH + gap) - g_scroll;
        if (yy + cardH < 0 || yy > H) continue;
        bool sel = rt::Eq(g_packs[i].id, g_set.pack);
        RECT r = { x, yy, x + cardW, yy + cardH };
        Box(dc, r, sel ? SEL : PANEL, sel ? SELLINE : LINE, Sc(12));
        if (HBITMAP b = LoadThumb(i, tw, th)) {
            HDC m = CreateCompatibleDC(dc); HGDIOBJ old = SelectObject(m, b);
            BitBlt(dc, x + Sc(6), yy + Sc(6), tw, th, m, 0, 0, SRCCOPY);
            SelectObject(m, old); DeleteDC(m);
        }
        RECT tr = { x + Sc(6), yy + th + Sc(12), x + cardW - Sc(6), yy + cardH - Sc(4) };
        SelectObject(dc, g_fNormal); SetTextColor(dc, TEXT);
        DrawTextW(dc, g_packs[i].name, -1, &tr, DT_CENTER | DT_END_ELLIPSIS | DT_SINGLELINE);
        AddHit(r.left, r.top, r.right, r.bottom, ID_PACK + i);
    }
    int rows = (g_packCount + perRow - 1) / perRow;
    y += rows * (cardH + gap);

    // ---- lighting: one set of choices drives the wallpaper, the phone and the keyboard
    Section(dc, L"LIGHTING", left, y, H);
    Text(dc, g_kbdOk ? L"Keyboard lit by AuraSync. Wallpaper and phone use the same settings."
                     : L"Keyboard not reachable (ASUS driver). Wallpaper and phone still work.",
         left, y - g_scroll, g_fNormal, MUTED);
    y += Sc(28);
    int x = left;
    for (int i = 0; i < FX_COUNT; ++i) Chip(dc, kEffectNames[i], x, y, left, right, g_light.effect == i, false, ID_EFFECT + i, H);
    y += Sc(34) + Sc(14);
    Text(dc, L"SPEED", left, y - g_scroll, g_fSmall, MUTED); y += Sc(24);
    x = left;
    for (int i = 0; i < 3; ++i) Chip(dc, kSpeedNames[i], x, y, left, right, g_light.speed == i, ghActive, ID_SPEED + i, H);
    y += Sc(34) + Sc(14);
    Text(dc, L"COLOR", left, y - g_scroll, g_fSmall, MUTED); y += Sc(24);
    x = left;
    int d = Sc(30);
    for (int i = 0; i < kColorCount; ++i) {
        if (x + d > right) { x = left; y += d + Sc(8); }
        int yy = y - g_scroll;
        if (yy + d > 0 && yy < H) {
            bool sel = g_light.color == kColors[i].c;
            HBRUSH b = CreateSolidBrush(kColors[i].c); HPEN p = CreatePen(PS_SOLID, sel ? Sc(3) : 1, sel ? RGB(255, 255, 255) : LINE);
            HGDIOBJ ob = SelectObject(dc, b), op = SelectObject(dc, p);
            Ellipse(dc, x, yy, x + d, yy + d);
            SelectObject(dc, ob); SelectObject(dc, op); DeleteObject(b); DeleteObject(p);
            AddHit(x, yy, x + d, yy + d, ID_COLOR + i);
        }
        x += d + Sc(10);
    }
    Chip(dc, L"Custom\x2026", x, y, left, right, false, ghActive, ID_COLOR_CUSTOM, H);
    y += d + Sc(8);

    // ---- phone and PC
    Section(dc, L"PHONE AND PC", left, y, H);
    x = left;
    Chip(dc, link::Paired() ? L"Show pairing code" : L"Pair phone\x2026", x, y, left, right, false, false, ID_PAIR, H);
    Chip(dc, L"Pause animation", x, y, left, right, g_set.paused != 0, false, ID_PAUSE, H);
    Chip(dc, L"Start with Windows", x, y, left, right, AutostartEnabled(), false, ID_AUTOSTART, H);
    y += Sc(34) + Sc(10);
    Text(dc, L"Closing this window leaves the wallpaper running. Use the tray icon to exit.", left, y - g_scroll, g_fSmall, MUTED);
    y += Sc(48);

    g_contentH = y;
    // thin scroll indicator
    if (g_contentH > H) {
        int bh = MulDiv(H, H, g_contentH), by = MulDiv(g_scroll, H, g_contentH);
        RECT sb = { W - Sc(6), by, W - Sc(2), by + bh };
        Fill(dc, sb, LINE);
    }
}

static void ClampScroll(int H) {
    int maxS = g_contentH - H; if (maxS < 0) maxS = 0;
    if (g_scroll > maxS) g_scroll = maxS;
    if (g_scroll < 0) g_scroll = 0;
}

static int HitTest(int mx, int my) {
    for (int i = g_nHits - 1; i >= 0; --i)
        if (mx >= g_hits[i].r.left && mx < g_hits[i].r.right && my >= g_hits[i].r.top && my < g_hits[i].r.bottom) return g_hits[i].id;
    return -1;
}

static void Act(int id) {
    bool ghActive = g_set.followGHelper && g_ghFound;
    if (id == ID_FOLLOW) { if (!g_set.followGHelper) OnCommand(ID_FOLLOW); }
    else if (id == ID_CHOOSE_HERE) { if (g_set.followGHelper) OnCommand(ID_FOLLOW); }
    else {
        // changing speed or colour by hand means leaving G-Helper's control
        if (ghActive && ((id >= ID_SPEED && id < ID_SPEED + 3) || (id >= ID_COLOR && id <= ID_COLOR_CUSTOM))) g_set.followGHelper = 0;
        OnCommand(id);
    }
}

static void FreeAll() {
    for (int i = 0; i < 64; ++i) if (g_thumbs[i]) { DeleteObject(g_thumbs[i]); g_thumbs[i] = nullptr; }
    if (g_back) { DeleteObject(g_back); g_back = nullptr; }
    HFONT* fs[] = { &g_fNormal, &g_fBold, &g_fTitle, &g_fSmall };
    for (HFONT* f : fs) if (*f) { DeleteObject(*f); *f = nullptr; }
    g_scroll = 0;
}

static LRESULT CALLBACK Proc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        HDC dc = GetDC(h); g_scale = MulDiv(100, GetDeviceCaps(dc, LOGPIXELSX), 96); ReleaseDC(h, dc);
        g_fNormal = CreateFontW(-Sc(15), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        g_fBold = CreateFontW(-Sc(15), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        g_fTitle = CreateFontW(-Sc(28), 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        g_fSmall = CreateFontW(-Sc(12), 0, 0, 0, FW_SEMIBOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        SetTimer(h, 1, 2000, nullptr);   // refresh the phone status line
        return 0;
    }
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps; HDC dc = BeginPaint(h, &ps);
        RECT rc; GetClientRect(h, &rc);
        int W = rc.right, H = rc.bottom;
        if (W > 0 && H > 0) {
            if (!g_back || g_backW != W || g_backH != H) {
                if (g_back) DeleteObject(g_back);
                g_back = CreateCompatibleBitmap(dc, W, H); g_backW = W; g_backH = H;
            }
            HDC m = CreateCompatibleDC(dc); HGDIOBJ old = SelectObject(m, g_back);
            ClampScroll(H);
            Paint(m, W, H);
            ClampScroll(H);
            BitBlt(dc, 0, 0, W, H, m, 0, 0, SRCCOPY);
            SelectObject(m, old); DeleteDC(m);
        }
        EndPaint(h, &ps);
        return 0;
    }
    case WM_SIZE: InvalidateRect(h, nullptr, FALSE); return 0;
    case WM_MOUSEWHEEL: {
        g_scroll -= (short)HIWORD(wp) * Sc(60) / 120;
        RECT rc; GetClientRect(h, &rc); ClampScroll(rc.bottom);
        InvalidateRect(h, nullptr, FALSE);
        return 0;
    }
    case WM_MOUSEMOVE: {
        int id = HitTest((short)LOWORD(lp), (short)HIWORD(lp));
        g_hover = id;
        return 0;
    }
    case WM_SETCURSOR:
        if (LOWORD(lp) == HTCLIENT) {
            POINT p; GetCursorPos(&p); ScreenToClient(h, &p);
            SetCursor(LoadCursorW(nullptr, HitTest(p.x, p.y) >= 0 ? MAKEINTRESOURCEW(32649) : MAKEINTRESOURCEW(32512)));
            return TRUE;
        }
        break;
    case WM_LBUTTONUP: {
        int id = HitTest((short)LOWORD(lp), (short)HIWORD(lp));
        if (id >= 0) { Act(id); InvalidateRect(h, nullptr, FALSE); }
        return 0;
    }
    case WM_TIMER: {
        int before = g_ghState;
        RefreshGHelper();
        if (g_ghState != before) ApplyLighting();   // G-Helper started or stopped: follow it at once
        InvalidateRect(h, nullptr, FALSE);
        return 0;
    }
    case WM_DESTROY:
        KillTimer(h, 1);
        FreeAll();
        g_uiWnd = nullptr;
        SetProcessWorkingSetSize(GetCurrentProcess(), (SIZE_T)-1, (SIZE_T)-1);   // hand the memory back
        return 0;
    }
    return DefWindowProcW(h, msg, wp, lp);
}

static void Open() {
    if (g_uiWnd) {
        ShowWindow(g_uiWnd, SW_RESTORE);
        SetForegroundWindow(g_uiWnd);
        return;
    }
    HDC dc = GetDC(nullptr); int dpi = GetDeviceCaps(dc, LOGPIXELSX); ReleaseDC(nullptr, dc);
    int w = MulDiv(820, dpi, 96), h = MulDiv(820, dpi, 96);
    int sw = GetSystemMetrics(SM_CXSCREEN), sh = GetSystemMetrics(SM_CYSCREEN);
    if (h > sh - 80) h = sh - 80;
    g_uiWnd = CreateWindowExW(0, L"AuraSyncUI", L"AuraSync", WS_OVERLAPPEDWINDOW | WS_VISIBLE,
                              (sw - w) / 2, (sh - h) / 2, w, h, nullptr, nullptr, g_inst, nullptr);
    if (g_uiWnd) {
        HICON ico = LoadIconW(g_inst, MAKEINTRESOURCEW(IDI_APP));
        SendMessageW(g_uiWnd, WM_SETICON, ICON_BIG, (LPARAM)ico);
        SendMessageW(g_uiWnd, WM_SETICON, ICON_SMALL, (LPARAM)ico);
        SetForegroundWindow(g_uiWnd);
    }
}

}  // namespace ui
