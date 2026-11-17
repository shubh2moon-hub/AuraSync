// Phone link: keeps the AuraSync phone app in step with the PC.
//
// Transport: public MQTT relays over secure WebSockets (WinHTTP), all three at once; messages are
// retained on the relay so the phone catches up whenever it connects. Everything is encrypted with
// AES-256-GCM (Windows CNG) using a key derived from a 10-character pairing code the user types into
// the phone once. Only changes are sent: the lighting state (~100 bytes) and, when the wallpaper or
// its phone framing changes, the phone images for that wallpaper (~0.6 MB, once).
#pragma once
#include <windows.h>
#include <winhttp.h>
#include <bcrypt.h>
#include "rt.h"


namespace link {

static const UINT WM_LINK_PACK = WM_APP + 3;   // phone picked a wallpaper; lParam unused, id in PhonePack()
static const DWORD CHUNK = 48000;               // one relay rejects retained messages above ~64 KB

struct Broker { const wchar_t* host; INTERNET_PORT port; const wchar_t* path; volatile LONG up; };
static Broker g_brokers[3] = {
    { L"broker.hivemq.com", 8884, L"/mqtt", 0 },
    { L"broker.emqx.io", 8084, L"/mqtt", 0 },
    { L"test.mosquitto.org", 8081, L"/mqtt", 0 },
};

static CRITICAL_SECTION g_cs;
static wchar_t g_dir[MAX_PATH];
static char g_code[16];          // pairing code, e.g. "K7Q2X9XMBP"
static BYTE g_key[32];
static char g_topic[48];         // "aps2/<20 hex>"
static char g_state[256];        // lighting + pack JSON
static BYTE* g_pack; static DWORD g_packLen;     // sealed phone pack
static char g_packInfo[200];
static volatile LONG g_gen;      // bumped on every change
static HANDLE g_wake;            // signalled on change / shutdown
static volatile bool g_running;
static HWND g_notify;
static char g_phonePack[64];
static volatile LONG g_phoneSeen;   // GetTickCount of the last phone check-in (0 = never)
static HINTERNET g_session;
static BCRYPT_ALG_HANDLE g_aes;

// ------------------------------------------------------------------ crypto

static void Sha256(const void* d, DWORD n, BYTE out[32]) {
    BCRYPT_ALG_HANDLE a; BCRYPT_HASH_HANDLE h;
    BCryptOpenAlgorithmProvider(&a, BCRYPT_SHA256_ALGORITHM, nullptr, 0);
    BCryptCreateHash(a, &h, nullptr, 0, nullptr, 0, 0);
    BCryptHashData(h, (PUCHAR)d, n, 0);
    BCryptFinishHash(h, out, 32, 0);
    BCryptDestroyHash(h);
    BCryptCloseAlgorithmProvider(a, 0);
}

static int Slen(const char* s) { int n = 0; while (s[n]) ++n; return n; }
static void Scpy(char* d, const char* s, int cap) { int i = 0; for (; s[i] && i < cap - 1; ++i) d[i] = s[i]; d[i] = 0; }
static void Scat(char* d, const char* s, int cap) { int n = Slen(d); Scpy(d + n, s, cap - n); }
static void Hex(const BYTE* b, int n, char* out) { const char* h = "0123456789abcdef"; for (int i = 0; i < n; ++i) { out[2 * i] = h[b[i] >> 4]; out[2 * i + 1] = h[b[i] & 15]; } out[2 * n] = 0; }
static void Num(char* out, long long v) {
    char t[24]; int n = 0; bool neg = v < 0; unsigned long long u = neg ? (unsigned long long)(-v) : (unsigned long long)v;
    do { t[n++] = (char)('0' + u % 10); u /= 10; } while (u);
    int i = 0; if (neg) out[i++] = '-'; while (n) out[i++] = t[--n]; out[i] = 0;
}

// Pairing code -> relay topic and encryption key (the phone derives the same).
static void DeriveFromCode() {
    char buf[64]; BYTE h[32];
    Scpy(buf, "aurasync-key:", 64); Scat(buf, g_code, 64);
    Sha256(buf, Slen(buf), g_key);
    Scpy(buf, "aurasync-topic:", 64); Scat(buf, g_code, 64);
    Sha256(buf, Slen(buf), h);
    Scpy(g_topic, "aps2/", 48);
    Hex(h, 10, g_topic + 5);
}

// nonce(12) | ciphertext | tag(16), AAD = message name
static BYTE* Seal(const char* name, const BYTE* pt, DWORD n, DWORD* outLen) {
    BYTE* out = (BYTE*)HeapAlloc(GetProcessHeap(), 0, n + 28);
    if (!out) return nullptr;
    BCryptGenRandom(nullptr, out, 12, BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    BCRYPT_KEY_HANDLE k;
    BCryptGenerateSymmetricKey(g_aes, &k, nullptr, 0, g_key, 32, 0);
    BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;
    BCRYPT_INIT_AUTH_MODE_INFO(info);
    info.pbNonce = out; info.cbNonce = 12;
    info.pbAuthData = (PUCHAR)name; info.cbAuthData = Slen(name);
    info.pbTag = out + 12 + n; info.cbTag = 16;
    ULONG done = 0;
    NTSTATUS st = BCryptEncrypt(k, (PUCHAR)pt, n, &info, nullptr, 0, out + 12, n, &done, 0);
    BCryptDestroyKey(k);
    if (st != 0) { HeapFree(GetProcessHeap(), 0, out); return nullptr; }
    *outLen = n + 28;
    return out;
}

static bool Open(const char* name, const BYTE* in, DWORD n, BYTE* out, DWORD cap, DWORD* outLen) {
    if (n < 28 || n - 28 > cap) return false;
    BCRYPT_KEY_HANDLE k;
    BCryptGenerateSymmetricKey(g_aes, &k, nullptr, 0, g_key, 32, 0);
    BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;
    BCRYPT_INIT_AUTH_MODE_INFO(info);
    info.pbNonce = (PUCHAR)in; info.cbNonce = 12;
    info.pbAuthData = (PUCHAR)name; info.cbAuthData = Slen(name);
    info.pbTag = (PUCHAR)in + n - 16; info.cbTag = 16;
    ULONG done = 0;
    NTSTATUS st = BCryptDecrypt(k, (PUCHAR)in + 12, n - 28, &info, nullptr, 0, out, cap, &done, 0);
    BCryptDestroyKey(k);
    *outLen = done;
    return st == 0;
}

// ------------------------------------------------------------------ pairing code

static void NewCode() {
    const char* abc = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";   // no 0/O/1/I
    BYTE r[10];
    BCryptGenRandom(nullptr, r, 10, BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    for (int i = 0; i < 10; ++i) g_code[i] = abc[r[i] & 31];
    g_code[10] = 0;
}

static void LoadOrCreateCode() {
    wchar_t p[MAX_PATH]; rt::Copy(p, g_dir, MAX_PATH); rt::Cat(p, L"\\pair.txt", MAX_PATH);
    char* s = rt::ReadFile(p, nullptr);
    if (s && Slen(s) >= 10) { for (int i = 0; i < 10; ++i) g_code[i] = s[i]; g_code[10] = 0; }
    else {
        NewCode();
        HANDLE f = CreateFileW(p, GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (f != INVALID_HANDLE_VALUE) { DWORD w; WriteFile(f, g_code, 10, &w, nullptr); CloseHandle(f); }
    }
    if (s) HeapFree(GetProcessHeap(), 0, s);
    DeriveFromCode();
}

// ------------------------------------------------------------------ MQTT over WebSocket

struct Conn { HINTERNET con, ws; Broker* b; volatile bool dead; BYTE* rx; DWORD rxLen; };

static bool WsSend(Conn* c, const BYTE* d, DWORD n) {
    return WinHttpWebSocketSend(c->ws, WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE, (PVOID)d, n) == NO_ERROR;
}

// header + remaining length + body
static bool MqttSend(Conn* c, BYTE header, const BYTE* a, DWORD an, const BYTE* b, DWORD bn) {
    DWORD len = an + bn;
    BYTE* pkt = (BYTE*)HeapAlloc(GetProcessHeap(), 0, len + 5);
    if (!pkt) return false;
    DWORD i = 0; pkt[i++] = header;
    DWORD x = len;
    do { BYTE d = x % 128; x /= 128; pkt[i++] = d | (x ? 0x80 : 0); } while (x);
    memcpy(pkt + i, a, an); memcpy(pkt + i + an, b, bn);
    bool ok = WsSend(c, pkt, i + len);
    HeapFree(GetProcessHeap(), 0, pkt);
    return ok;
}

static DWORD PutStr(BYTE* p, const char* s) { DWORD n = Slen(s); p[0] = (BYTE)(n >> 8); p[1] = (BYTE)n; memcpy(p + 2, s, n); return n + 2; }

static bool Publish(Conn* c, const char* name, const BYTE* payload, DWORD n) {
    char topic[96]; Scpy(topic, g_topic, 96); Scat(topic, "/", 96); Scat(topic, name, 96);
    BYTE head[100]; DWORD hn = PutStr(head, topic);
    return MqttSend(c, 0x31, head, hn, payload, n);   // PUBLISH, QoS 0, retained
}

static bool Subscribe(Conn* c, const char* name) {
    char topic[96]; Scpy(topic, g_topic, 96); Scat(topic, "/", 96); Scat(topic, name, 96);
    BYTE b[110]; b[0] = 0; b[1] = 1; DWORD n = 2 + PutStr(b + 2, topic); b[n++] = 0;
    return MqttSend(c, 0x82, b, n, nullptr, 0);
}

static bool Connect(Conn* c) {
    c->con = WinHttpConnect(g_session, c->b->host, c->b->port, 0);
    if (!c->con) return false;
    HINTERNET req = WinHttpOpenRequest(c->con, L"GET", c->b->path, nullptr, nullptr, nullptr, WINHTTP_FLAG_SECURE);
    if (!req) return false;
    WinHttpSetOption(req, WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, nullptr, 0);
    bool ok = WinHttpSendRequest(req, L"Sec-WebSocket-Protocol: mqtt\r\n", (DWORD)-1L, nullptr, 0, 0, 0) &&
              WinHttpReceiveResponse(req, nullptr);
    if (ok) c->ws = WinHttpWebSocketCompleteUpgrade(req, 0);
    WinHttpCloseHandle(req);
    if (!c->ws) return false;
    // CONNECT: clean session, keep-alive 120 s, random client id
    BYTE body[64]; DWORD n = PutStr(body, "MQTT");
    body[n++] = 4; body[n++] = 0x02; body[n++] = 0; body[n++] = 120;
    BYTE r[6]; char id[16] = "aspc-"; BCryptGenRandom(nullptr, r, 5, BCRYPT_USE_SYSTEM_PREFERRED_RNG); Hex(r, 5, id + 5);
    n += PutStr(body + n, id);
    if (!MqttSend(c, 0x10, body, n, nullptr, 0)) return false;
    BYTE ack[8]; DWORD got = 0; WINHTTP_WEB_SOCKET_BUFFER_TYPE t;
    if (WinHttpWebSocketReceive(c->ws, ack, sizeof(ack), &got, &t) != NO_ERROR || got < 4 || ack[0] != 0x20 || ack[3] != 0) return false;
    return Subscribe(c, "cmd");
}

static void Disconnect(Conn* c) {
    if (c->ws) { WinHttpWebSocketClose(c->ws, WINHTTP_WEB_SOCKET_SUCCESS_CLOSE_STATUS, nullptr, 0); WinHttpCloseHandle(c->ws); c->ws = nullptr; }
    if (c->con) { WinHttpCloseHandle(c->con); c->con = nullptr; }
}

static void Changed();

// Messages from the phone: {"hello":1} when it connects, {"pack":"<id>"} when the user picks a wallpaper there.
static void OnPhoneMessage(const BYTE* payload, DWORD n) {
    BYTE plain[512]; DWORD pn = 0;
    if (!Open("cmd", payload, n, plain, sizeof(plain) - 1, &pn)) return;
    plain[pn] = 0;
    InterlockedExchange(&g_phoneSeen, (LONG)GetTickCount() | 1);
    wchar_t id[64];
    if (rt::JsonString((const char*)plain, "pack", id, 64)) {
        EnterCriticalSection(&g_cs);
        WideCharToMultiByte(CP_UTF8, 0, id, -1, g_phonePack, 64, nullptr, nullptr);
        LeaveCriticalSection(&g_cs);
        PostMessageW(g_notify, WM_LINK_PACK, 0, 0);
    } else {
        Changed();
    }
}

static DWORD WINAPI Receiver(LPVOID p) {
    Conn* c = (Conn*)p;
    BYTE buf[4096];
    for (;;) {
        DWORD got = 0; WINHTTP_WEB_SOCKET_BUFFER_TYPE t;
        if (WinHttpWebSocketReceive(c->ws, buf, sizeof(buf), &got, &t) != NO_ERROR || t == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) break;
        if (c->rxLen + got > 65536) c->rxLen = 0;            // nothing we expect is this big
        memcpy(c->rx + c->rxLen, buf, got); c->rxLen += got;
        for (;;) {   // parse complete MQTT packets
            if (c->rxLen < 2) break;
            DWORD len = 0, mult = 1, i = 1;
            while (i < c->rxLen && i < 5) { len += (c->rx[i] & 127) * mult; mult *= 128; if (!(c->rx[i++] & 128)) break; }
            if (i >= c->rxLen && (c->rx[i - 1] & 128)) break;
            if (c->rxLen < i + len) break;
            BYTE type = c->rx[0] & 0xF0;
            if (type == 0x30 && len >= 2) {
                DWORD tl = (c->rx[i] << 8) | c->rx[i + 1];
                DWORD off = i + 2 + tl + (((c->rx[0] >> 1) & 3) ? 2 : 0);
                if (off <= i + len && tl >= 4 && memcmp(c->rx + i + 2 + tl - 4, "/cmd", 4) == 0)
                    OnPhoneMessage(c->rx + off, i + len - off);
            }
            memmove(c->rx, c->rx + i + len, c->rxLen - i - len);
            c->rxLen -= i + len;
        }
    }
    c->dead = true;
    SetEvent(g_wake);
    return 0;
}

// Publishes the latest state (and pack, if it changed since this relay last got it).
static bool PushAll(Conn* c, char* lastPackInfo) {
    EnterCriticalSection(&g_cs);
    char state[256]; Scpy(state, g_state, 256);
    char info[200]; Scpy(info, g_packInfo, 200);
    BYTE* pack = nullptr; DWORD packLen = g_packLen;
    bool newPack = g_pack && info[0] && memcmp(info, lastPackInfo, Slen(info) + 1) != 0;   // not yet on this relay
    if (newPack) { pack = (BYTE*)HeapAlloc(GetProcessHeap(), 0, packLen); if (pack) memcpy(pack, g_pack, packLen); }
    LeaveCriticalSection(&g_cs);
    bool ok = true;
    if (newPack && pack) {
        for (DWORD off = 0, i = 0; ok && off < packLen; off += CHUNK, ++i) {
            char name[24] = "pack/"; char num[12]; Num(num, i); Scat(name, num, 24);
            ok = Publish(c, name, pack + off, packLen - off < CHUNK ? packLen - off : CHUNK);
        }
        DWORD sn; BYTE* s = Seal("pack/info", (const BYTE*)info, Slen(info), &sn);
        if (ok && s) ok = Publish(c, "pack/info", s, sn);
        if (s) HeapFree(GetProcessHeap(), 0, s);
        if (ok) Scpy(lastPackInfo, info, 200);
    }
    if (pack) HeapFree(GetProcessHeap(), 0, pack);
    if (ok && state[0]) {
        DWORD sn; BYTE* s = Seal("state", (const BYTE*)state, Slen(state), &sn);
        if (s) { ok = Publish(c, "state", s, sn); HeapFree(GetProcessHeap(), 0, s); }
    }
    return ok;
}

static DWORD WINAPI BrokerThread(LPVOID p) {
    Broker* b = (Broker*)p;
    DWORD backoff = 3000;
    while (g_running) {
        Conn c = {}; c.b = b;
        c.rx = (BYTE*)HeapAlloc(GetProcessHeap(), 0, 65536 + 4096);
        char lastPack[200] = "";
        if (c.rx && Connect(&c)) {
            InterlockedExchange(&b->up, 1);
            backoff = 3000;
            HANDLE rx = CreateThread(nullptr, 64 * 1024, Receiver, &c, STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
            LONG sent = -1;
            DWORD lastPing = GetTickCount();
            while (g_running && !c.dead) {
                LONG gen = g_gen;
                if (gen != sent) { if (!PushAll(&c, lastPack)) break; sent = gen; }
                if (GetTickCount() - lastPing > 60000) { BYTE ping[2] = { 0xC0, 0 }; if (!WsSend(&c, ping, 2)) break; lastPing = GetTickCount(); }
                WaitForSingleObject(g_wake, 5000);
            }
            InterlockedExchange(&b->up, 0);
            Disconnect(&c);
            if (rx) { WaitForSingleObject(rx, 5000); CloseHandle(rx); }
        } else {
            Disconnect(&c);
        }
        if (c.rx) HeapFree(GetProcessHeap(), 0, c.rx);
        // wait before retrying, waking early on shutdown
        DWORD until = GetTickCount() + backoff;
        while (g_running && (LONG)(until - GetTickCount()) > 0) WaitForSingleObject(g_wake, 1000);
        backoff = backoff < 120000 ? backoff * 2 : 120000;
    }
    return 0;
}

// ------------------------------------------------------------------ API used by main.cpp

static HANDLE g_threads[3];

inline void SetStateDir(const wchar_t* dir) { rt::Copy(g_dir, dir, MAX_PATH); }

inline void Start(HWND notify) {
    g_notify = notify;
    InitializeCriticalSection(&g_cs);
    BCryptOpenAlgorithmProvider(&g_aes, BCRYPT_AES_ALGORITHM, nullptr, 0);
    BCryptSetProperty(g_aes, BCRYPT_CHAINING_MODE, (PUCHAR)BCRYPT_CHAIN_MODE_GCM, sizeof(BCRYPT_CHAIN_MODE_GCM), 0);
    LoadOrCreateCode();
    g_session = WinHttpOpen(L"AuraSync/1.0", WINHTTP_ACCESS_TYPE_DEFAULT_PROXY, WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    g_wake = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    g_running = true;
    for (int i = 0; i < 3; ++i)
        g_threads[i] = CreateThread(nullptr, 64 * 1024, BrokerThread, &g_brokers[i], STACK_SIZE_PARAM_IS_A_RESERVATION, nullptr);
}

inline void Stop() {
    g_running = false;
    for (int i = 0; i < 6; ++i) SetEvent(g_wake);
    WaitForMultipleObjects(3, g_threads, TRUE, 4000);
    if (g_session) WinHttpCloseHandle(g_session);
}

inline void Poll() {}

inline bool Paired() { return g_phoneSeen != 0; }

inline int RelaysUp() { int n = 0; for (int i = 0; i < 3; ++i) n += g_brokers[i].up ? 1 : 0; return n; }

inline void PhonePack(wchar_t* out, int cap) {
    EnterCriticalSection(&g_cs);
    MultiByteToWideChar(CP_UTF8, 0, g_phonePack, -1, out, cap);
    LeaveCriticalSection(&g_cs);
}

static void Changed() { InterlockedIncrement(&g_gen); SetEvent(g_wake); SetEvent(g_wake); SetEvent(g_wake); }

static char g_packId[64];
static int g_effect, g_speed; static COLORREF g_color; static long long g_epoch;

static void RebuildState() {
    char n[24];
    Scpy(g_state, "{\"pack\":\"", 256); Scat(g_state, g_packId, 256);
    Scat(g_state, "\",\"effect\":", 256); Num(n, g_effect); Scat(g_state, n, 256);
    Scat(g_state, ",\"speed\":", 256); Num(n, g_speed); Scat(g_state, n, 256);
    Scat(g_state, ",\"color\":", 256); Num(n, (long long)((GetRValue(g_color) << 16) | (GetGValue(g_color) << 8) | GetBValue(g_color))); Scat(g_state, n, 256);
    Scat(g_state, ",\"epoch\":", 256); Num(n, g_epoch); Scat(g_state, n, 256);
    Scat(g_state, "}", 256);
}

static bool g_lightingSet;
inline void PublishLighting(int effect, int speed, COLORREF color, long long epoch) {
    if (!g_session) return;
    EnterCriticalSection(&g_cs);
    if (g_lightingSet && g_effect == effect && g_speed == speed && g_color == color) {   // nothing changed: do not wake the phone
        LeaveCriticalSection(&g_cs);
        return;
    }
    g_lightingSet = true;
    g_effect = effect; g_speed = speed; g_color = color; g_epoch = epoch;
    RebuildState();
    LeaveCriticalSection(&g_cs);
    Changed();
}

// Packs the phone images of a wallpaper: "ASP1" then (u16 name len, name, u32 data len, data) xN.
inline void PublishPack(const wchar_t* packsDir, const wchar_t* id) {
    if (!g_session) return;
    const wchar_t* fileNames[6] = { L"meta.json", L"phone_base.jpg", L"phone_light.jpg", L"phone_land_base.jpg", L"phone_land_light.jpg", L"phone_preview.jpg" };
    const wchar_t* files[6] = {};
    char* data[6] = {}; DWORD len[6] = {}; DWORD total = 4;
    int fileCount = 0;
    for (int i = 0; i < 6; ++i) {
        wchar_t p[MAX_PATH]; rt::Path(p, packsDir, id, fileNames[i]);
        DWORD flen = 0;
        char* d = rt::ReadFile(p, &flen);
        if (d) {
            data[fileCount] = d;
            len[fileCount] = flen;
            files[fileCount] = fileNames[i];
            total += 2 + rt::Len(fileNames[i]) + 4 + flen;
            fileCount++;
        } else if (i < 3) {
            for (int j = 0; j < fileCount; ++j) HeapFree(GetProcessHeap(), 0, data[j]);
            return;
        }
    }
    BYTE* blob = (BYTE*)HeapAlloc(GetProcessHeap(), 0, total);
    DWORD o = 0;
    memcpy(blob, "ASP1", 4); o = 4;
    for (int i = 0; i < fileCount; ++i) {
        char name[32]; WideCharToMultiByte(CP_UTF8, 0, files[i], -1, name, 32, nullptr, nullptr);
        DWORD nl = Slen(name);
        blob[o++] = (BYTE)(nl >> 8); blob[o++] = (BYTE)nl; memcpy(blob + o, name, nl); o += nl;
        blob[o++] = (BYTE)(len[i] >> 24); blob[o++] = (BYTE)(len[i] >> 16); blob[o++] = (BYTE)(len[i] >> 8); blob[o++] = (BYTE)len[i];
        memcpy(blob + o, data[i], len[i]); o += len[i];
    }
    // the phone skips the download when its copy of meta.json (which holds the framing) is identical
    BYTE h[32]; Sha256(data[0], len[0], h);
    char hex[17]; Hex(h, 8, hex);
    for (int i = 0; i < fileCount; ++i) HeapFree(GetProcessHeap(), 0, data[i]);
    DWORD sealedLen; BYTE* sealed = Seal("pack", blob, total, &sealedLen);
    HeapFree(GetProcessHeap(), 0, blob);
    if (!sealed) return;
    char idA[64]; WideCharToMultiByte(CP_UTF8, 0, id, -1, idA, 64, nullptr, nullptr);
    char n[16];
    EnterCriticalSection(&g_cs);
    if (g_pack) HeapFree(GetProcessHeap(), 0, g_pack);
    g_pack = sealed; g_packLen = sealedLen;
    Scpy(g_packId, idA, 64);
    Scpy(g_packInfo, "{\"id\":\"", 200); Scat(g_packInfo, idA, 200);
    Scat(g_packInfo, "\",\"meta\":\"", 200); Scat(g_packInfo, hex, 200);
    Scat(g_packInfo, "\",\"size\":", 200); Num(n, sealedLen); Scat(g_packInfo, n, 200);
    Scat(g_packInfo, ",\"chunks\":", 200); Num(n, (sealedLen + CHUNK - 1) / CHUNK); Scat(g_packInfo, n, 200);
    Scat(g_packInfo, "}", 200);
    RebuildState();
    LeaveCriticalSection(&g_cs);
    Changed();
}

inline void ShowPairing(HWND owner) {
    wchar_t msg[512], code[16];
    for (int i = 0; i < 10; ++i) code[i] = (wchar_t)g_code[i];
    code[10] = 0;
    wchar_t pretty[16];
    for (int i = 0, j = 0; i < 10; ++i) { pretty[j++] = code[i]; if (i == 4) pretty[j++] = L'-'; pretty[j] = 0; }
    rt::Copy(msg, L"Pairing code:   ", 512);
    rt::Cat(msg, pretty, 512);
    rt::Cat(msg, L"\n\nOn your phone, open AuraSync, tap \x201CPair with PC\x201D and type this code. You only do this once.\n\n", 512);
    rt::Cat(msg, Paired() ? L"Status: your phone has checked in." : L"Status: waiting for the phone.", 512);
    int up = RelaysUp();
    wchar_t num[8]; rt::IntToStr(num, up);
    rt::Cat(msg, L"\nInternet relays connected: ", 512); rt::Cat(msg, num, 512); rt::Cat(msg, L" of 3.", 512);
    MessageBoxW(owner, msg, L"AuraSync \x2013 pair your phone", MB_ICONINFORMATION);
}

}  // namespace link
