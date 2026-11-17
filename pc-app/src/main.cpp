// AuraSync for Windows: draws an AuraSync library wallpaper behind the desktop icons with live
// lighting effects, following G-Helper's keyboard lighting when it is installed.
// Built without the C runtime to keep memory use minimal (see build.bat).

#define WIN32_LEAN_AND_MEAN
#define D3D11_NO_HELPERS
#define NOMINMAX
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wincodec.h>
#include <shellapi.h>
#include <shlobj.h>
#include <commdlg.h>
#include <tlhelp32.h>
#include "aura_vs.h"
#include "aura_ps.h"
#include "../res/resource.h"
#include "rt.h"
#include "link.h"

// ------------------------------------------------------------------ state

enum Effect { FX_STATIC, FX_BREATHE, FX_CYCLE, FX_STROBE, FX_RAINBOW, FX_COMET, FX_COUNT };
static const wchar_t* kEffectNames[FX_COUNT] = { L"Static", L"Breathe", L"Color Cycle", L"Strobe", L"Rainbow", L"Comet" };
static const bool kAnimated[FX_COUNT] = { false, true, true, true, true, true };
static const float kSpeeds[3] = { 0.5f, 1.0f, 2.0f };
static const wchar_t* kSpeedNames[3] = { L"Slow", L"Normal", L"Fast" };
static const struct { const wchar_t* name; COLORREF c; } kColors[] = {
    { L"Red", RGB(0xff, 0x2a, 0x3a) }, { L"Orange", RGB(0xff, 0x6a, 0x00) }, { L"Yellow", RGB(0xff, 0xd4, 0x00) },
    { L"Green", RGB(0x2b, 0xff, 0x88) }, { L"Cyan", RGB(0x00, 0xe5, 0xff) }, { L"Blue", RGB(0x3d, 0x7b, 0xff) },
    { L"Violet", RGB(0x7a, 0x5c, 0xff) }, { L"Pink", RGB(0xff, 0x2f, 0xb4) }, { L"White", RGB(0xff, 0xff, 0xff) },
};
static const int kColorCount = sizeof(kColors) / sizeof(kColors[0]);

struct Settings {
    wchar_t pack[64];
    int followGHelper;      // 1: lighting comes from G-Helper's config
    int effect, speed;      // used when not following G-Helper
    COLORREF color;
    int paused;
    int keyboard;           // 1: AuraSync lights the keyboard; 0: another app (G-Helper) owns it
};

struct Pack { wchar_t id[64]; wchar_t name[64]; };

static Settings g_set;
static Pack g_packs[64];
static int g_packCount;
static wchar_t g_packsDir[MAX_PATH], g_iniPath[MAX_PATH], g_ghPath[MAX_PATH], g_ghDir[MAX_PATH];

struct Lighting { int effect, speed; COLORREF color; };
static Lighting g_light;          // what is on screen right now
static bool g_ghFound;

static HWND g_msgWnd, g_wallWnd, g_uiWnd;
static HINSTANCE g_inst;
static UINT g_taskbarCreated;
static NOTIFYICONDATAW g_nid;
static int g_screenW, g_screenH;
static bool g_covered;            // a maximized / fullscreen window hides the desktop

// ------------------------------------------------------------------ D3D

static ID3D11Device* g_dev;
static ID3D11DeviceContext* g_ctx;
static IDXGISwapChain1* g_swap;
static ID3D11RenderTargetView* g_rtv;
static ID3D11VertexShader* g_vs;
static ID3D11PixelShader* g_ps;
static ID3D11SamplerState* g_samp;
static ID3D11Buffer* g_cb;
static ID3D11ShaderResourceView* g_baseSrv;
static ID3D11ShaderResourceView* g_lightSrv;

struct CB { float time, speed; int effect; float fade; float color[3]; float x0; float x1; float pad[3]; };

template <class T> static void Release(T*& p) { if (p) { p->Release(); p = nullptr; } }

// Unix milliseconds, the same clock the phone uses.
static long long NowMs() {
    FILETIME ft; GetSystemTimeAsFileTime(&ft);
    ULONGLONG t = (((ULONGLONG)ft.dwHighDateTime) << 32) | ft.dwLowDateTime;
    return (long long)(t / 10000ULL) - 11644473600000LL;
}
static long long g_epochMs;   // when the current lighting started; the wallpaper, phone and keyboard all count from here

// Seconds since the lighting started, wrapped to an hour (the same wrap the phone uses).
static float EffectSeconds() {
    long long el = (NowMs() - g_epochMs) % 3600000LL;
    if (el < 0) el += 3600000LL;
    return (float)el / 1000.0f;
}

static IDXGIAdapter1* PickAdapter(IDXGIFactory1* f) {
    // The adapter that drives the screen (usually the integrated GPU on laptops: lowest power).
    IDXGIAdapter1* a = nullptr;
    for (UINT i = 0; f->EnumAdapters1(i, &a) != DXGI_ERROR_NOT_FOUND; ++i) {
        IDXGIOutput* o = nullptr;
        if (SUCCEEDED(a->EnumOutputs(0, &o))) { o->Release(); return a; }
        a->Release();
    }
    return nullptr;
}

static bool InitD3D(HWND hwnd) {
    IDXGIFactory2* factory = nullptr;
    if (FAILED(CreateDXGIFactory1(__uuidof(IDXGIFactory2), (void**)&factory))) return false;
    IDXGIAdapter1* adapter = PickAdapter(factory);
    D3D_FEATURE_LEVEL levels[] = { D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_1, D3D_FEATURE_LEVEL_10_0 };
    HRESULT hr = D3D11CreateDevice(adapter, adapter ? D3D_DRIVER_TYPE_UNKNOWN : D3D_DRIVER_TYPE_HARDWARE, nullptr,
                                   D3D11_CREATE_DEVICE_SINGLETHREADED, levels, 3, D3D11_SDK_VERSION, &g_dev, nullptr, &g_ctx);
    if (adapter) adapter->Release();
    if (FAILED(hr)) { factory->Release(); return false; }

    DXGI_SWAP_CHAIN_DESC1 sd = {};
    sd.Width = g_screenW; sd.Height = g_screenH;
    sd.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
    hr = factory->CreateSwapChainForHwnd(g_dev, hwnd, &sd, nullptr, nullptr, &g_swap);
    factory->MakeWindowAssociation(hwnd, DXGI_MWA_NO_ALT_ENTER);
    factory->Release();
    if (FAILED(hr)) return false;

    ID3D11Texture2D* bb = nullptr;
    g_swap->GetBuffer(0, __uuidof(ID3D11Texture2D), (void**)&bb);
    g_dev->CreateRenderTargetView(bb, nullptr, &g_rtv);
    bb->Release();

    g_dev->CreateVertexShader(g_VSMain, sizeof(g_VSMain), nullptr, &g_vs);
    g_dev->CreatePixelShader(g_PSMain, sizeof(g_PSMain), nullptr, &g_ps);

    D3D11_SAMPLER_DESC ss = {};
    ss.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    ss.AddressU = ss.AddressV = ss.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    ss.MaxLOD = D3D11_FLOAT32_MAX;
    g_dev->CreateSamplerState(&ss, &g_samp);

    D3D11_BUFFER_DESC bd = {};
    bd.ByteWidth = sizeof(CB);
    bd.Usage = D3D11_USAGE_DYNAMIC;
    bd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    bd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    g_dev->CreateBuffer(&bd, nullptr, &g_cb);
    return true;
}

// Decodes an image with WIC, crops it to the screen's aspect, scales it to the screen and uploads it.
static ID3D11ShaderResourceView* LoadTexture(const wchar_t* path, bool gray) {
    IWICImagingFactory* wic = nullptr;
    if (FAILED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wic)))) return nullptr;
    ID3D11ShaderResourceView* srv = nullptr;
    IWICBitmapDecoder* dec = nullptr; IWICBitmapFrameDecode* frame = nullptr;
    IWICBitmapClipper* clip = nullptr; IWICBitmapScaler* scaler = nullptr; IWICFormatConverter* conv = nullptr;
    UINT w = 0, h = 0;
    if (SUCCEEDED(wic->CreateDecoderFromFilename(path, nullptr, GENERIC_READ, WICDecodeMetadataCacheOnDemand, &dec)) &&
        SUCCEEDED(dec->GetFrame(0, &frame)) && SUCCEEDED(frame->GetSize(&w, &h))) {
        // crop to the screen aspect ratio
        WICRect r = { 0, 0, (INT)w, (INT)h };
        if ((ULONGLONG)w * g_screenH > (ULONGLONG)h * g_screenW) { r.Width = (INT)((ULONGLONG)h * g_screenW / g_screenH); r.X = ((INT)w - r.Width) / 2; }
        else { r.Height = (INT)((ULONGLONG)w * g_screenH / g_screenW); r.Y = ((INT)h - r.Height) / 2; }
        wic->CreateBitmapClipper(&clip);
        clip->Initialize(frame, &r);
        wic->CreateBitmapScaler(&scaler);
        scaler->Initialize(clip, g_screenW, g_screenH, WICBitmapInterpolationModeFant);
        wic->CreateFormatConverter(&conv);
        if (SUCCEEDED(conv->Initialize(scaler, gray ? GUID_WICPixelFormat8bppGray : GUID_WICPixelFormat32bppRGBA,
                                       WICBitmapDitherTypeNone, nullptr, 0, WICBitmapPaletteTypeCustom))) {
            UINT bpp = gray ? 1 : 4, stride = g_screenW * bpp, size = stride * g_screenH;
            void* px = HeapAlloc(GetProcessHeap(), 0, size);
            if (px && SUCCEEDED(conv->CopyPixels(nullptr, stride, size, (BYTE*)px))) {
                D3D11_TEXTURE2D_DESC td = {};
                td.Width = g_screenW; td.Height = g_screenH; td.MipLevels = 1; td.ArraySize = 1;
                td.Format = gray ? DXGI_FORMAT_R8_UNORM : DXGI_FORMAT_R8G8B8A8_UNORM;
                td.SampleDesc.Count = 1; td.Usage = D3D11_USAGE_IMMUTABLE; td.BindFlags = D3D11_BIND_SHADER_RESOURCE;
                D3D11_SUBRESOURCE_DATA init = { px, stride, 0 };
                ID3D11Texture2D* tex = nullptr;
                if (SUCCEEDED(g_dev->CreateTexture2D(&td, &init, &tex))) {
                    g_dev->CreateShaderResourceView(tex, nullptr, &srv);
                    tex->Release();
                }
            }
            if (px) HeapFree(GetProcessHeap(), 0, px);   // pixels now live on the GPU only
        }
    }
    Release(conv); Release(scaler); Release(clip); Release(frame); Release(dec); Release(wic);
    return srv;
}

static bool LoadPack(const wchar_t* id) {
    wchar_t base[MAX_PATH], light[MAX_PATH];
    rt::Path(base, g_packsDir, id, L"pc_base.jpg");
    rt::Path(light, g_packsDir, id, L"pc_light.jpg");
    ID3D11ShaderResourceView* b = LoadTexture(base, false);
    ID3D11ShaderResourceView* l = LoadTexture(light, true);
    if (!b || !l) { Release(b); Release(l); return false; }
    // Unbind and flush so the driver frees the old wallpaper now rather than whenever it likes.
    ID3D11ShaderResourceView* none[2] = { nullptr, nullptr };
    g_ctx->PSSetShaderResources(0, 2, none);
    Release(g_baseSrv); Release(g_lightSrv);
    g_ctx->Flush();
    g_baseSrv = b; g_lightSrv = l;
    SetProcessWorkingSetSize(GetCurrentProcess(), (SIZE_T)-1, (SIZE_T)-1);
    return true;
}

// ------------------------------------------------------------------ keyboard (built in)

// The TUF keyboard is lit through the ASUS driver (ATKACPI), the same call G-Helper makes.
static HANDLE g_atk = INVALID_HANDLE_VALUE;
static bool g_kbdOk;             // the last write to the keyboard succeeded

static bool KbdOpen() {
    if (g_atk == INVALID_HANDLE_VALUE)
        g_atk = CreateFileW(L"\\\\.\\ATKACPI", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    return g_atk != INVALID_HANDLE_VALUE;
}

static void PutU32(BYTE* p, DWORD v) { p[0] = (BYTE)v; p[1] = (BYTE)(v >> 8); p[2] = (BYTE)(v >> 16); p[3] = (BYTE)(v >> 24); }

// Method DEVS on device 0x00100056 (TUF keyboard) with six bytes: B4, mode, R, G, B, speed.
static bool KbdWrite(int mode, COLORREF c, int speedCode) {
    if (!KbdOpen()) return false;
    const DWORD kDevs = 0x53564544, kTufKb = 0x00100056, kControl = 0x0022240C;
    BYTE in[18] = {};
    PutU32(in, kDevs); PutU32(in + 4, 10); PutU32(in + 8, kTufKb);
    in[12] = 0xB4; in[13] = (BYTE)mode; in[14] = GetRValue(c); in[15] = GetGValue(c); in[16] = GetBValue(c); in[17] = (BYTE)speedCode;
    BYTE out[16] = {}; DWORD ret = 0;
    if (!DeviceIoControl(g_atk, kControl, in, sizeof(in), out, sizeof(out), &ret, nullptr)) return false;
    return out[0] == 1 && out[1] == 0 && out[2] == 0 && out[3] == 0;   // the driver returns 1 on success
}

// Keyboard modes: 0 static, 1 breathe, 2 colour cycle, 10 strobe. The TUF keyboard has no rainbow or comet,
// so those fall back to colour cycle and breathe.
static int KbdMode(int effect) {
    switch (effect) {
        case FX_BREATHE: return 1;
        case FX_CYCLE:   return 2;
        case FX_STROBE:  return 10;
        case FX_RAINBOW: return 2;
        case FX_COMET:   return 1;
        default:         return 0;
    }
}

static int KbdSpeed(int speed) { return speed == 0 ? 0xe1 : speed == 2 ? 0xf5 : 0xeb; }

static void KbdApply(const Lighting& l) {
    g_kbdOk = KbdWrite(KbdMode(l.effect), l.color, KbdSpeed(l.speed));
}

static void Draw() {
    if (!g_swap || !g_baseSrv) return;
    D3D11_MAPPED_SUBRESOURCE m;
    if (SUCCEEDED(g_ctx->Map(g_cb, 0, D3D11_MAP_WRITE_DISCARD, 0, &m))) {
        CB* cb = (CB*)m.pData;
        rt::Zero(cb, sizeof(CB));
        cb->time = EffectSeconds();
        cb->speed = kSpeeds[g_light.speed];
        cb->effect = g_light.effect;
        cb->color[0] = GetRValue(g_light.color) / 255.0f;
        cb->color[1] = GetGValue(g_light.color) / 255.0f;
        cb->color[2] = GetBValue(g_light.color) / 255.0f;
        cb->x0 = 0.0f; cb->x1 = 1.0f;
        g_ctx->Unmap(g_cb, 0);
    }
    D3D11_VIEWPORT vp = { 0, 0, (float)g_screenW, (float)g_screenH, 0, 1 };
    g_ctx->RSSetViewports(1, &vp);
    g_ctx->OMSetRenderTargets(1, &g_rtv, nullptr);
    g_ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    g_ctx->VSSetShader(g_vs, nullptr, 0);
    g_ctx->PSSetShader(g_ps, nullptr, 0);
    ID3D11ShaderResourceView* srvs[2] = { g_baseSrv, g_lightSrv };
    g_ctx->PSSetShaderResources(0, 2, srvs);
    g_ctx->PSSetSamplers(0, 1, &g_samp);
    g_ctx->PSSetConstantBuffers(0, 1, &g_cb);
    g_ctx->Draw(3, 0);
    // vsync-paced, aiming for 60 fps (not 144+): one sync per 60 Hz of the display's refresh rate
    static UINT interval = 0;
    if (!interval) {
        HDC dc = GetDC(nullptr);
        int hz = dc ? GetDeviceCaps(dc, VREFRESH) : 60;
        if (dc) ReleaseDC(nullptr, dc);
        interval = hz >= 90 ? (UINT)((hz + 30) / 60) : 1;
    }
    g_swap->Present(interval, 0);
}

static void ShutdownD3D() {
    Release(g_baseSrv); Release(g_lightSrv); Release(g_cb); Release(g_samp); Release(g_ps); Release(g_vs);
    Release(g_rtv); Release(g_swap);
    if (g_ctx) g_ctx->ClearState();
    Release(g_ctx); Release(g_dev);
}

// ------------------------------------------------------------------ desktop layer

static HWND FindWallpaperHost() {
    HWND progman = FindWindowW(L"Progman", nullptr);
    if (!progman) return nullptr;
    // Ask Explorer to create the WorkerW layer that sits between the wallpaper and the icons.
    DWORD_PTR r;
    SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, SMTO_NORMAL, 1000, &r);
    SendMessageTimeoutW(progman, 0x052C, 0, 0, SMTO_NORMAL, 1000, &r);
    // Windows 11 24H2 and later: the WorkerW is a child of Progman, below the icon view.
    HWND w = FindWindowExW(progman, nullptr, L"WorkerW", nullptr);
    if (w) return w;
    // Earlier builds: the top-level WorkerW that follows the one hosting the icons.
    struct S { static BOOL CALLBACK Cb(HWND h, LPARAM lp) {
        if (FindWindowExW(h, nullptr, L"SHELLDLL_DefView", nullptr)) {
            *(HWND*)lp = FindWindowExW(nullptr, h, L"WorkerW", nullptr);
            return FALSE;
        }
        return TRUE; } };
    EnumWindows(S::Cb, (LPARAM)&w);
    return w ? w : progman;
}

static LRESULT CALLBACK WallProc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_ERASEBKGND) return 1;
    if (msg == WM_PAINT) { PAINTSTRUCT ps; BeginPaint(h, &ps); EndPaint(h, &ps); Draw(); return 0; }
    return DefWindowProcW(h, msg, wp, lp);
}

static bool CreateWallpaper() {
    HWND host = FindWallpaperHost();
    if (!host) return false;
    RECT rc; GetClientRect(host, &rc);
    g_screenW = rc.right - rc.left; g_screenH = rc.bottom - rc.top;
    if (g_screenW <= 0 || g_screenH <= 0) { g_screenW = GetSystemMetrics(SM_CXSCREEN); g_screenH = GetSystemMetrics(SM_CYSCREEN); }
    g_wallWnd = CreateWindowExW(WS_EX_NOACTIVATE, L"AuraSyncWall", L"AuraSync", WS_CHILD | WS_VISIBLE,
                                0, 0, g_screenW, g_screenH, host, nullptr, g_inst, nullptr);
    if (!g_wallWnd) return false;
    SetWindowPos(g_wallWnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    return InitD3D(g_wallWnd);
}

// ------------------------------------------------------------------ library, settings, G-Helper

static void ScanLibrary() {
    g_packCount = 0;
    wchar_t pattern[MAX_PATH];
    rt::Path(pattern, g_packsDir, L"*", nullptr);
    WIN32_FIND_DATAW fd;
    HANDLE f = FindFirstFileW(pattern, &fd);
    if (f == INVALID_HANDLE_VALUE) return;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || fd.cFileName[0] == L'.') continue;
        wchar_t meta[MAX_PATH];
        rt::Path(meta, g_packsDir, fd.cFileName, L"meta.json");
        char* json = rt::ReadFile(meta, nullptr);
        if (!json) continue;
        Pack& p = g_packs[g_packCount];
        rt::Copy(p.id, fd.cFileName, 64);
        if (!rt::JsonString(json, "name", p.name, 64)) rt::Copy(p.name, fd.cFileName, 64);
        HeapFree(GetProcessHeap(), 0, json);
        if (++g_packCount == 64) break;
    } while (FindNextFileW(f, &fd));
    FindClose(f);
}

// ------------------------------------------------------------------ G-Helper

static wchar_t g_ghExe[MAX_PATH];   // GHelper.exe: from the running process, the saved setting, or the Locate dialog
static int g_ghState;               // 0 not found, 1 installed but not running, 2 running

static void SetGHelperExe(const wchar_t* exe) {
    rt::Copy(g_ghExe, exe, MAX_PATH);
    rt::Copy(g_ghDir, exe, MAX_PATH); rt::DirName(g_ghDir);
    // a portable G-Helper keeps config.json next to GHelper.exe
    wchar_t cfg[MAX_PATH]; rt::Path(cfg, g_ghDir, L"config.json", nullptr);
    if (GetFileAttributesW(cfg) != INVALID_FILE_ATTRIBUTES) rt::Copy(g_ghPath, cfg, MAX_PATH);
}

// Looks for a running GHelper.exe; otherwise checks whether it is installed where we know to look.
static void RefreshGHelper() {
    int state = 0;
    wchar_t running[MAX_PATH] = {};
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap != INVALID_HANDLE_VALUE) {
        PROCESSENTRY32W pe = {}; pe.dwSize = sizeof(pe);
        if (Process32FirstW(snap, &pe)) do {
            if (rt::Eq(pe.szExeFile, L"GHelper.exe")) {
                HANDLE p = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
                if (p) { DWORD n = MAX_PATH; QueryFullProcessImageNameW(p, 0, running, &n); CloseHandle(p); }
                state = 2;
                break;
            }
        } while (Process32NextW(snap, &pe));
        CloseHandle(snap);
    }
    if (state == 2 && running[0]) SetGHelperExe(running);
    if (state == 0) {
        if (g_ghExe[0] && GetFileAttributesW(g_ghExe) != INVALID_FILE_ATTRIBUTES) state = 1;
        else if (GetFileAttributesW(g_ghPath) != INVALID_FILE_ATTRIBUTES) state = 1;
    }
    g_ghState = state;
}

static void LaunchGHelper() {
    if (!g_ghExe[0] || GetFileAttributesW(g_ghExe) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(g_uiWnd ? g_uiWnd : g_msgWnd, L"Locate GHelper.exe first, then AuraSync can open it.",
                    L"AuraSync", MB_ICONINFORMATION);
        return;
    }
    wchar_t dir[MAX_PATH]; rt::Copy(dir, g_ghExe, MAX_PATH); rt::DirName(dir);
    ShellExecuteW(nullptr, L"open", g_ghExe, nullptr, dir, SW_SHOWNORMAL);
}

static void LoadSettings() {
    GetPrivateProfileStringW(L"AuraSync", L"pack", L"", g_set.pack, 64, g_iniPath);
    g_set.followGHelper = 0;   // G-Helper is no longer needed; AuraSync lights the keyboard itself
    g_set.effect = GetPrivateProfileIntW(L"AuraSync", L"effect", FX_RAINBOW, g_iniPath);
    g_set.speed = GetPrivateProfileIntW(L"AuraSync", L"speed", 1, g_iniPath);
    g_set.color = (COLORREF)GetPrivateProfileIntW(L"AuraSync", L"color", (int)RGB(0xff, 0x2a, 0x3a), g_iniPath);
    g_set.paused = GetPrivateProfileIntW(L"AuraSync", L"paused", 0, g_iniPath);
    g_set.keyboard = GetPrivateProfileIntW(L"AuraSync", L"keyboard", 1, g_iniPath);
    // Portable G-Helper keeps config.json next to GHelper.exe; let settings.ini point there.
    wchar_t gh[MAX_PATH];
    if (GetPrivateProfileStringW(L"AuraSync", L"ghelper_config", L"", gh, MAX_PATH, g_iniPath) > 0) {
        rt::Copy(g_ghPath, gh, MAX_PATH);
        rt::Copy(g_ghDir, gh, MAX_PATH);
        rt::DirName(g_ghDir);
    }
    wchar_t ge[MAX_PATH];
    if (GetPrivateProfileStringW(L"AuraSync", L"ghelper_exe", L"", ge, MAX_PATH, g_iniPath) > 0) SetGHelperExe(ge);
    if (g_set.effect < 0 || g_set.effect >= FX_COUNT) g_set.effect = FX_RAINBOW;
    if (g_set.speed < 0 || g_set.speed > 2) g_set.speed = 1;
}

static void SaveSettings() {
    wchar_t n[16];
    WritePrivateProfileStringW(L"AuraSync", L"pack", g_set.pack, g_iniPath);
    rt::IntToStr(n, g_set.followGHelper); WritePrivateProfileStringW(L"AuraSync", L"follow_ghelper", n, g_iniPath);
    rt::IntToStr(n, g_set.effect); WritePrivateProfileStringW(L"AuraSync", L"effect", n, g_iniPath);
    rt::IntToStr(n, g_set.speed); WritePrivateProfileStringW(L"AuraSync", L"speed", n, g_iniPath);
    rt::IntToStr(n, (int)g_set.color); WritePrivateProfileStringW(L"AuraSync", L"color", n, g_iniPath);
    rt::IntToStr(n, g_set.paused); WritePrivateProfileStringW(L"AuraSync", L"paused", n, g_iniPath);
    if (g_ghExe[0]) WritePrivateProfileStringW(L"AuraSync", L"ghelper_exe", g_ghExe, g_iniPath);
}

static void ApplyLighting();

static void LocateGHelper() {
    wchar_t file[MAX_PATH] = {};
    OPENFILENAMEW ofn = {};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = g_uiWnd ? g_uiWnd : g_msgWnd;
    ofn.lpstrFilter = L"GHelper.exe\0GHelper.exe\0Programs (*.exe)\0*.exe\0\0";
    ofn.lpstrFile = file; ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&ofn)) return;
    SetGHelperExe(file);
    SaveSettings();
    RefreshGHelper();
    ApplyLighting();
}

// G-Helper keyboard modes -> AuraSync effects (AuraMode enum in G-Helper's Aura.cs).
static int MapGHelperMode(int m) {
    switch (m) {
        case 0: return FX_STATIC;  case 1: return FX_BREATHE; case 2: return FX_CYCLE;
        case 3: return FX_RAINBOW; case 10: return FX_STROBE; case 11: return FX_COMET;
        default: return FX_STATIC;   // heatmap, battery, audio...: hold the chosen colour
    }
}

// G-Helper saves its settings in several steps, so a read can catch the file half-written or
// without the lighting keys yet. Retry briefly, and keep whatever the last good values were for
// any key that is missing, so the wallpaper and the phone do not jump to a default and back.
static bool ReadGHelper(Lighting* out) {
    for (int attempt = 0; attempt < 5; ++attempt) {
        if (attempt) Sleep(60);
        char* json = rt::ReadFile(g_ghPath, nullptr);
        if (!json) continue;
        long long mode = 0, color = 0, speed = 0;
        bool hasMode = rt::JsonInt(json, "aura_mode", &mode);
        bool hasColor = rt::JsonInt(json, "aura_color", &color);
        bool hasSpeed = rt::JsonInt(json, "aura_speed", &speed);
        HeapFree(GetProcessHeap(), 0, json);
        if (!hasMode) continue;
        out->effect = MapGHelperMode((int)mode);
        if (hasColor) {
            unsigned argb = (unsigned)(color & 0xFFFFFFFF);
            out->color = RGB((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF);
        }
        if (hasSpeed && speed >= 0 && speed <= 2) out->speed = (int)speed;
        return true;
    }
    return false;
}

static void UpdateTooltip();

// Decides what is on screen from settings and G-Helper, then redraws.
static void ApplyLighting() {
    Lighting l = { g_set.effect, g_set.speed, g_set.color };
    bool changed = l.effect != g_light.effect || l.speed != g_light.speed || l.color != g_light.color;
    if (changed || g_epochMs == 0) {
        g_epochMs = NowMs();          // restart the shared clock: the wallpaper, phone and keyboard all start together
        g_light = l;
        if (g_set.keyboard) KbdApply(g_light);
    }
    link::PublishLighting(g_light.effect, g_light.speed, g_light.color, g_epochMs);
    UpdateTooltip();
    if (g_wallWnd) InvalidateRect(g_wallWnd, nullptr, FALSE);
    if (g_uiWnd) InvalidateRect(g_uiWnd, nullptr, FALSE);
}

static bool Animating() { return kAnimated[g_light.effect] && !g_set.paused && !g_covered; }

// Is the desktop hidden by a maximized or full-screen window? Then skip animation work.
static bool DesktopCovered() {
    QUERY_USER_NOTIFICATION_STATE st;
    if (SUCCEEDED(SHQueryUserNotificationState(&st)) &&
        (st == QUNS_RUNNING_D3D_FULL_SCREEN || st == QUNS_PRESENTATION_MODE || st == QUNS_BUSY)) return true;
    HWND fg = GetForegroundWindow();
    if (!fg) return false;
    wchar_t cls[64]; GetClassNameW(fg, cls, 64);
    if (rt::Eq(cls, L"Progman") || rt::Eq(cls, L"WorkerW") || rt::Eq(cls, L"Shell_TrayWnd")) return false;
    if (IsZoomed(fg)) return true;
    RECT r; GetWindowRect(fg, &r);
    return r.left <= 0 && r.top <= 0 && r.right >= g_screenW && r.bottom >= g_screenH;
}

// ------------------------------------------------------------------ tray

enum {
    ID_PACK = 1000, ID_FOLLOW = 1100, ID_EFFECT = 1200, ID_SPEED = 1300, ID_COLOR = 1400, ID_COLOR_CUSTOM = 1499,
    ID_PAUSE = 1500, ID_AUTOSTART = 1501, ID_GALLERY = 1502, ID_PAIR = 1503, ID_OPEN = 1504, ID_EXIT = 1599, ID_GH_OPEN = 1505, ID_GH_LOCATE = 1506,
};
static const UINT WM_TRAY = WM_APP + 1;
static const wchar_t* kRunKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";

static bool AutostartEnabled() {
    HKEY k; bool on = false;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, kRunKey, 0, KEY_READ, &k) == ERROR_SUCCESS) {
        on = RegQueryValueExW(k, L"AuraSync", nullptr, nullptr, nullptr, nullptr) == ERROR_SUCCESS;
        RegCloseKey(k);
    }
    return on;
}

static void SetAutostart(bool on) {
    HKEY k;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, kRunKey, 0, KEY_SET_VALUE, &k) != ERROR_SUCCESS) return;
    if (on) {
        wchar_t exe[MAX_PATH + 2], quoted[MAX_PATH + 4];
        GetModuleFileNameW(nullptr, exe, MAX_PATH);
        quoted[0] = L'"'; rt::Copy(quoted + 1, exe, MAX_PATH); rt::Cat(quoted, L"\"", MAX_PATH + 4);
        RegSetValueExW(k, L"AuraSync", 0, REG_SZ, (const BYTE*)quoted, (rt::Len(quoted) + 1) * sizeof(wchar_t));
    } else {
        RegDeleteValueW(k, L"AuraSync");
    }
    RegCloseKey(k);
}

static const wchar_t* CurrentPackName() {
    for (int i = 0; i < g_packCount; ++i) if (rt::Eq(g_packs[i].id, g_set.pack)) return g_packs[i].name;
    return L"(no wallpaper)";
}

static void UpdateTooltip() {
    if (!g_nid.hWnd) return;
    wchar_t tip[128];
    rt::Copy(tip, L"AuraSync \x2013 ", 128);
    rt::Cat(tip, CurrentPackName(), 128);
    rt::Cat(tip, L"\n", 128);
    rt::Cat(tip, kEffectNames[g_light.effect], 128);
    rt::Cat(tip, g_ghFound ? L" (G-Helper)" : (g_set.followGHelper ? L" (G-Helper not found)" : L""), 128);
    if (g_set.paused) rt::Cat(tip, L", paused", 128);
    rt::Copy(g_nid.szTip, tip, 128);
    g_nid.uFlags = NIF_TIP;
    Shell_NotifyIconW(NIM_MODIFY, &g_nid);
}

static void AddTrayIcon() {
    g_nid.cbSize = sizeof(g_nid);
    g_nid.hWnd = g_msgWnd;
    g_nid.uID = 1;
    g_nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    g_nid.uCallbackMessage = WM_TRAY;
    g_nid.hIcon = (HICON)LoadImageW(g_inst, MAKEINTRESOURCEW(IDI_APP), IMAGE_ICON,
                                    GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), 0);
    rt::Copy(g_nid.szTip, L"AuraSync", 128);
    Shell_NotifyIconW(NIM_ADD, &g_nid);
    UpdateTooltip();
}

static void ShowMenu() {
    HMENU m = CreatePopupMenu();
    HMENU packs = CreatePopupMenu();
    for (int i = 0; i < g_packCount; ++i)
        AppendMenuW(packs, MF_STRING | (rt::Eq(g_packs[i].id, g_set.pack) ? MF_CHECKED : 0), ID_PACK + i, g_packs[i].name);
    if (!g_packCount) AppendMenuW(packs, MF_STRING | MF_GRAYED, 0, L"No wallpapers found");

    HMENU light = CreatePopupMenu();
    AppendMenuW(light, MF_STRING | (g_set.followGHelper ? MF_CHECKED : 0), ID_FOLLOW,
                g_set.followGHelper && !g_ghFound ? L"Follow G-Helper (not found)" : L"Follow G-Helper keyboard lighting");
    AppendMenuW(light, MF_SEPARATOR, 0, nullptr);
    for (int i = 0; i < FX_COUNT; ++i)
        AppendMenuW(light, MF_STRING | (!g_set.followGHelper && g_set.effect == i ? MF_CHECKED : 0), ID_EFFECT + i, kEffectNames[i]);

    HMENU speed = CreatePopupMenu();
    for (int i = 0; i < 3; ++i)
        AppendMenuW(speed, MF_STRING | (g_set.speed == i ? MF_CHECKED : 0), ID_SPEED + i, kSpeedNames[i]);
    HMENU color = CreatePopupMenu();
    for (int i = 0; i < kColorCount; ++i)
        AppendMenuW(color, MF_STRING | (g_set.color == kColors[i].c ? MF_CHECKED : 0), ID_COLOR + i, kColors[i].name);
    AppendMenuW(color, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(color, MF_STRING, ID_COLOR_CUSTOM, L"Custom...");

    AppendMenuW(m, MF_STRING | MF_DEFAULT, ID_OPEN, L"Open AuraSync window");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_POPUP, (UINT_PTR)packs, L"Wallpaper");
    AppendMenuW(m, MF_POPUP, (UINT_PTR)light, L"Lighting");
    AppendMenuW(m, MF_POPUP | (g_set.followGHelper && g_ghFound ? MF_GRAYED : 0), (UINT_PTR)color, L"Color");
    AppendMenuW(m, MF_POPUP | (g_set.followGHelper && g_ghFound ? MF_GRAYED : 0), (UINT_PTR)speed, L"Speed");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, ID_PAIR, link::Paired() ? L"Phone: paired (show pairing code)" : L"Pair phone...");
    AppendMenuW(m, MF_STRING, ID_GALLERY, L"Open wallpaper gallery");
    AppendMenuW(m, MF_STRING | (g_set.paused ? MF_CHECKED : 0), ID_PAUSE, L"Pause animation");
    AppendMenuW(m, MF_STRING | (AutostartEnabled() ? MF_CHECKED : 0), ID_AUTOSTART, L"Start with Windows");
    AppendMenuW(m, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(m, MF_STRING, ID_EXIT, L"Exit");

    POINT pt; GetCursorPos(&pt);
    SetForegroundWindow(g_msgWnd);
    TrackPopupMenu(m, TPM_RIGHTBUTTON, pt.x, pt.y, 0, g_msgWnd, nullptr);
    PostMessageW(g_msgWnd, WM_NULL, 0, 0);
    DestroyMenu(m);   // destroys the submenus too
}

static void SelectPack(int i) {
    if (i < 0 || i >= g_packCount) return;
    if (LoadPack(g_packs[i].id)) {
        rt::Copy(g_set.pack, g_packs[i].id, 64);
        SaveSettings();
        link::PublishPack(g_packsDir, g_set.pack);
        UpdateTooltip();
        InvalidateRect(g_wallWnd, nullptr, FALSE);
        if (g_uiWnd) InvalidateRect(g_uiWnd, nullptr, FALSE);
    }
}

static void OpenUi();

static void OnCommand(int id) {
    if (id >= ID_PACK && id < ID_PACK + g_packCount) { SelectPack(id - ID_PACK); return; }
    if (id == ID_FOLLOW) g_set.followGHelper = !g_set.followGHelper;
    else if (id >= ID_EFFECT && id < ID_EFFECT + FX_COUNT) { g_set.effect = id - ID_EFFECT; g_set.followGHelper = 0; }
    else if (id >= ID_SPEED && id < ID_SPEED + 3) g_set.speed = id - ID_SPEED;
    else if (id >= ID_COLOR && id < ID_COLOR + kColorCount) g_set.color = kColors[id - ID_COLOR].c;
    else if (id == ID_COLOR_CUSTOM) {
        static COLORREF custom[16];
        CHOOSECOLORW cc = {};
        cc.lStructSize = sizeof(cc); cc.hwndOwner = g_uiWnd ? g_uiWnd : g_msgWnd; cc.rgbResult = g_set.color;
        cc.lpCustColors = custom; cc.Flags = CC_FULLOPEN | CC_RGBINIT;
        if (!ChooseColorW(&cc)) return;
        g_set.color = cc.rgbResult;
    }
    else if (id == ID_PAUSE) g_set.paused = !g_set.paused;
    else if (id == ID_AUTOSTART) { SetAutostart(!AutostartEnabled()); return; }
    else if (id == ID_GALLERY) {
        // The gallery (phone framing, effect previews) is served by library\serve.py.
        wchar_t lib[MAX_PATH], args[MAX_PATH + 16];
        rt::Copy(lib, g_packsDir, MAX_PATH); rt::DirName(lib);
        args[0] = L'"'; args[1] = 0; rt::Cat(args, lib, MAX_PATH + 16); rt::Cat(args, L"\\serve.py\"", MAX_PATH + 16);
        if ((INT_PTR)ShellExecuteW(nullptr, L"open", L"pythonw.exe", args, lib, SW_HIDE) > 32) {
            Sleep(800);
            ShellExecuteW(nullptr, L"open", L"http://127.0.0.1:8765/", nullptr, nullptr, SW_SHOWNORMAL);
        } else {
            ShellExecuteW(nullptr, L"open", g_packsDir, nullptr, nullptr, SW_SHOWNORMAL);
        }
        return;
    }
    else if (id == ID_GH_OPEN) { LaunchGHelper(); return; }
    else if (id == ID_GH_LOCATE) { LocateGHelper(); return; }
    else if (id == ID_PAIR) { link::ShowPairing(g_uiWnd ? g_uiWnd : g_msgWnd); return; }
    else if (id == ID_OPEN) { OpenUi(); return; }
    else if (id == ID_EXIT) { DestroyWindow(g_msgWnd); return; }
    SaveSettings();
    ApplyLighting();
}

#include "ui.h"
static void OpenUi() { ui::Open(); }

static LRESULT CALLBACK MsgProc(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_TRAY) {
        if (LOWORD(lp) == WM_RBUTTONUP) ShowMenu();
        else if (LOWORD(lp) == WM_LBUTTONUP) OpenUi();
        return 0;
    }
    if (msg == WM_APP + 3) { OpenUi(); return 0; }
    if (msg == WM_COMMAND) { OnCommand(LOWORD(wp)); return 0; }
    if (msg == link::WM_LINK_PACK) {   // wallpaper picked on the phone
        wchar_t id[64]; link::PhonePack(id, 64);
        for (int i = 0; i < g_packCount; ++i) if (rt::Eq(g_packs[i].id, id) && !rt::Eq(id, g_set.pack)) SelectPack(i);
        return 0;
    }
    if (msg == WM_DISPLAYCHANGE) { PostMessageW(h, WM_APP + 2, 0, 0); return 0; }
    if (msg == WM_APP + 2 || (g_taskbarCreated && msg == g_taskbarCreated)) {
        // Explorer restarted or the screen changed: rebuild the desktop layer and tray icon.
        if (g_wallWnd) { ShutdownD3D(); DestroyWindow(g_wallWnd); g_wallWnd = nullptr; }
        if (CreateWallpaper()) {
            for (int i = 0; i < g_packCount; ++i) if (rt::Eq(g_packs[i].id, g_set.pack)) LoadPack(g_packs[i].id);
        }
        if (msg == g_taskbarCreated) AddTrayIcon();
        ApplyLighting();
        return 0;
    }
    if (msg == WM_DESTROY) {
        Shell_NotifyIconW(NIM_DELETE, &g_nid);
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, msg, wp, lp);
}

// ------------------------------------------------------------------ main

static void ResolvePaths() {
    wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
    rt::DirName(exe);
    // installed: <exe dir>\library\packs ; development: <repo>\library\packs
    const wchar_t* tries[] = { L"\\library\\packs", L"\\..\\library\\packs", L"\\..\\..\\library\\packs" };
    for (const wchar_t* t : tries) {
        wchar_t p[MAX_PATH]; rt::Copy(p, exe, MAX_PATH); rt::Cat(p, t, MAX_PATH);
        wchar_t full[MAX_PATH];
        if (GetFullPathNameW(p, MAX_PATH, full, nullptr) && (GetFileAttributesW(full) & FILE_ATTRIBUTE_DIRECTORY)
            && GetFileAttributesW(full) != INVALID_FILE_ATTRIBUTES) { rt::Copy(g_packsDir, full, MAX_PATH); break; }
    }
    wchar_t appdata[MAX_PATH];
    SHGetFolderPathW(nullptr, CSIDL_APPDATA, nullptr, 0, appdata);
    rt::Copy(g_iniPath, appdata, MAX_PATH); rt::Cat(g_iniPath, L"\\AuraSync", MAX_PATH);
    CreateDirectoryW(g_iniPath, nullptr);
    link::SetStateDir(g_iniPath);
    rt::Cat(g_iniPath, L"\\settings.ini", MAX_PATH);
    rt::Copy(g_ghDir, appdata, MAX_PATH); rt::Cat(g_ghDir, L"\\GHelper", MAX_PATH);
    rt::Copy(g_ghPath, g_ghDir, MAX_PATH); rt::Cat(g_ghPath, L"\\config.json", MAX_PATH);
}

static int Run() {
    HANDLE single = CreateMutexW(nullptr, TRUE, L"AuraSync.SingleInstance");
    if (GetLastError() == ERROR_ALREADY_EXISTS) {   // already running: just show its window
        HWND other = FindWindowW(L"AuraSyncMsg", nullptr);
        if (other) PostMessageW(other, WM_APP + 3, 0, 0);
        return 0;
    }
    SetProcessDPIAware();
    CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    g_inst = GetModuleHandleW(nullptr);
    ResolvePaths();
    LoadSettings();
    RefreshGHelper();
    ScanLibrary();

    WNDCLASSW wc = {};
    wc.lpfnWndProc = WallProc; wc.hInstance = g_inst; wc.lpszClassName = L"AuraSyncWall";
    RegisterClassW(&wc);
    wc.lpfnWndProc = MsgProc; wc.lpszClassName = L"AuraSyncMsg";
    RegisterClassW(&wc);
    wc.lpfnWndProc = ui::Proc; wc.lpszClassName = L"AuraSyncUI";
    RegisterClassW(&wc);
    g_msgWnd = CreateWindowExW(0, L"AuraSyncMsg", L"AuraSync", 0, 0, 0, 0, 0, nullptr, nullptr, g_inst, nullptr);
    g_taskbarCreated = RegisterWindowMessageW(L"TaskbarCreated");

    // At sign-in Explorer may not have built the desktop layer yet, so keep trying for a minute before giving up.
    bool attached = false;
    for (int attempt = 0; attempt < 60 && !attached; ++attempt) {
        attached = CreateWallpaper();
        if (!attached) Sleep(1000);
    }
    if (!attached) {
        MessageBoxW(nullptr, L"AuraSync couldn't attach to the desktop.", L"AuraSync", MB_ICONERROR);
        return 1;
    }
    int start = 0;
    for (int i = 0; i < g_packCount; ++i) if (rt::Eq(g_packs[i].id, g_set.pack)) start = i;
    link::Start(g_msgWnd);
    if (g_packCount) SelectPack(start);
    AddTrayIcon();
    ApplyLighting();
    SetProcessWorkingSetSize(GetCurrentProcess(), (SIZE_T)-1, (SIZE_T)-1);   // drop start-up pages

    // Watch our own settings folder: G-Helper's Wallpaper window edits settings.ini there.
    wchar_t setDir[MAX_PATH]; rt::Copy(setDir, g_iniPath, MAX_PATH); rt::DirName(setDir);
    HANDLE ghWatch = FindFirstChangeNotificationW(setDir, FALSE, FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_FILE_NAME);
    DWORD lastCoverCheck = 0;
    for (;;) {
        DWORD now = GetTickCount();
        if (now - lastCoverCheck > 1000) {
            lastCoverCheck = now;
            bool c = DesktopCovered();
            if (c != g_covered) { g_covered = c; if (!c) InvalidateRect(g_wallWnd, nullptr, FALSE); }
        }
        DWORD timeout = Animating() ? 1 : 1000;
        HANDLE hs[1]; DWORD n = 0;
        if (ghWatch != INVALID_HANDLE_VALUE) hs[n++] = ghWatch;
        DWORD r = MsgWaitForMultipleObjects(n, hs, FALSE, timeout, QS_ALLINPUT);
        if (n && r == WAIT_OBJECT_0) {
            Sleep(100);   // let the writer finish
            wchar_t oldPack[64]; rt::Copy(oldPack, g_set.pack, 64);
            LoadSettings();
            if (!rt::Eq(oldPack, g_set.pack))
                for (int i = 0; i < g_packCount; ++i) if (rt::Eq(g_packs[i].id, g_set.pack)) SelectPack(i);
            ApplyLighting();
            if (!FindNextChangeNotification(ghWatch)) { FindCloseChangeNotification(ghWatch); ghWatch = INVALID_HANDLE_VALUE; }
        }
        MSG m;
        while (PeekMessageW(&m, nullptr, 0, 0, PM_REMOVE)) {
            if (m.message == WM_QUIT) goto done;
            TranslateMessage(&m);
            DispatchMessageW(&m);
        }
        link::Poll();
        if (Animating()) Draw();
    }
done:
    link::Stop();
    if (ghWatch != INVALID_HANDLE_VALUE) FindCloseChangeNotification(ghWatch);
    ShutdownD3D();
    if (g_wallWnd) DestroyWindow(g_wallWnd);
    CoUninitialize();
    CloseHandle(single);
    return 0;
}

extern "C" void __stdcall WinMainCRTStartup() { ExitProcess((UINT)Run()); }
