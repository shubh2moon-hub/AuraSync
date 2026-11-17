#pragma once
#include <vcruntime.h>
#ifdef __cplusplus
extern "C" {
#endif
void* __cdecl memcpy(void*, const void*, size_t);
void* __cdecl memset(void*, int, size_t);
void* __cdecl memmove(void*, const void*, size_t);
int __cdecl memcmp(const void*, const void*, size_t);
int __cdecl _wcsicmp(const wchar_t*, const wchar_t*);
size_t __cdecl wcslen(const wchar_t*);
size_t __cdecl strlen(const char*);
#ifdef __cplusplus
}
#endif
