// Tiny replacements for the few C runtime pieces AuraSync needs (it links no CRT).
#pragma once
#include <windows.h>
#include <intrin.h>

extern "C" {
int _fltused = 0;
#pragma function(memset, memcpy, memcmp, memmove)
// rep stosb / movsb: the compiler can't turn these back into calls to themselves
void* __cdecl memset(void* d, int v, size_t n) { __stosb((unsigned char*)d, (unsigned char)v, n); return d; }
void* __cdecl memcpy(void* d, const void* s, size_t n) { __movsb((unsigned char*)d, (const unsigned char*)s, n); return d; }
void* __cdecl memmove(void* d, const void* s, size_t n) {
    unsigned char* a = (unsigned char*)d; const unsigned char* b = (const unsigned char*)s;
    if (a < b) while (n--) *a++ = *b++; else { a += n; b += n; while (n--) *--a = *--b; }
    return d;
}
int __cdecl memcmp(const void* x, const void* y, size_t n) {
    const unsigned char* a = (const unsigned char*)x; const unsigned char* b = (const unsigned char*)y;
    for (; n; --n, ++a, ++b) if (*a != *b) return *a - *b;
    return 0;
}
}

namespace rt {

inline void Zero(void* p, size_t n) { memset(p, 0, n); }
inline int Len(const wchar_t* s) { int n = 0; while (s[n]) ++n; return n; }
inline bool Eq(const wchar_t* a, const wchar_t* b) { while (*a && *a == *b) { ++a; ++b; } return *a == *b; }

inline void Copy(wchar_t* d, const wchar_t* s, int cap) {
    int i = 0;
    for (; s[i] && i < cap - 1; ++i) d[i] = s[i];
    d[i] = 0;
}
inline void Cat(wchar_t* d, const wchar_t* s, int cap) { int n = Len(d); Copy(d + n, s, cap - n); }

inline void Path(wchar_t* out, const wchar_t* dir, const wchar_t* a, const wchar_t* b) {
    Copy(out, dir, MAX_PATH); Cat(out, L"\\", MAX_PATH); Cat(out, a, MAX_PATH);
    if (b) { Cat(out, L"\\", MAX_PATH); Cat(out, b, MAX_PATH); }
}

inline void DirName(wchar_t* p) { int n = Len(p); while (n > 0 && p[n - 1] != L'\\') --n; if (n > 0) p[n - 1] = 0; }

inline void IntToStr(wchar_t* out, long long v) {
    wchar_t tmp[24]; int n = 0; bool neg = v < 0;
    unsigned long long u = neg ? (unsigned long long)(-v) : (unsigned long long)v;
    do { tmp[n++] = (wchar_t)(L'0' + u % 10); u /= 10; } while (u);
    int i = 0; if (neg) out[i++] = L'-';
    while (n) out[i++] = tmp[--n];
    out[i] = 0;
}

// Reads a whole file, NUL-terminated. Caller frees with HeapFree(GetProcessHeap()).
inline char* ReadFile(const wchar_t* path, DWORD* size) {
    HANDLE f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr,
                           OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE) return nullptr;
    DWORD n = GetFileSize(f, nullptr), got = 0;
    char* buf = (n != INVALID_FILE_SIZE && n < (64u << 20)) ? (char*)HeapAlloc(GetProcessHeap(), 0, n + 1) : nullptr;
    if (buf && ::ReadFile(f, buf, n, &got, nullptr)) buf[got] = 0;
    else if (buf) { HeapFree(GetProcessHeap(), 0, buf); buf = nullptr; }
    CloseHandle(f);
    if (size) *size = got;
    return buf;
}

// Finds "key": in flat JSON and returns a pointer just after the colon.
inline const char* JsonFind(const char* json, const char* key) {
    int kl = 0; while (key[kl]) ++kl;
    for (const char* p = json; *p; ++p) {
        if (*p != '"') continue;
        int i = 0; while (i < kl && p[1 + i] == key[i]) ++i;
        if (i == kl && p[1 + kl] == '"') {
            const char* q = p + 2 + kl;
            while (*q == ' ' || *q == '\t' || *q == '\r' || *q == '\n') ++q;
            if (*q == ':') { ++q; while (*q == ' ' || *q == '\t' || *q == '\r' || *q == '\n') ++q; return q; }
        }
    }
    return nullptr;
}

inline bool JsonInt(const char* json, const char* key, long long* out) {
    const char* p = JsonFind(json, key);
    if (!p) return false;
    bool neg = false;
    if (*p == '"') ++p;               // tolerate numbers stored as strings
    if (*p == '-') { neg = true; ++p; }
    if (*p < '0' || *p > '9') return false;
    long long v = 0;
    while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
    *out = neg ? -v : v;
    return true;
}

inline bool JsonString(const char* json, const char* key, wchar_t* out, int cap) {
    const char* p = JsonFind(json, key);
    if (!p || *p != '"') return false;
    ++p;
    const char* e = p;
    while (*e && *e != '"') { if (*e == '\\' && e[1]) ++e; ++e; }
    int n = MultiByteToWideChar(CP_UTF8, 0, p, (int)(e - p), out, cap - 1);
    out[n] = 0;
    return true;
}

}  // namespace rt
