@echo off
rem Builds AuraSync.exe with MSVC Build Tools + Windows 8.1 SDK, without the C runtime.
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>nul
set SDK=C:\Program Files (x86)\Windows Kits\8.1
set INCLUDE=%~dp0crtshim;%VCToolsInstallDir%include;%SDK%\Include\um;%SDK%\Include\shared
set LIB=%SDK%\Lib\winv6.3\um\x64
cd /d "%~dp0"
if not exist build mkdir build
"%SDK%\bin\x64\fxc.exe" /nologo /T vs_4_0 /E VSMain /O3 /Vn g_VSMain /Fh build\aura_vs.h src\aura.hlsl || exit /b 1
"%SDK%\bin\x64\fxc.exe" /nologo /T ps_4_0 /E PSMain /O3 /Vn g_PSMain /Fh build\aura_ps.h src\aura.hlsl || exit /b 1
"%SDK%\bin\x64\rc.exe" /nologo /fo build\app.res res\app.rc || exit /b 1
cl /nologo /c /O1 /GS- /Gs999999 /EHs-c- /GR- /W3 /Zl /I build src\main.cpp /Fo:build\main.obj || exit /b 1
link /nologo /NODEFAULTLIB /ENTRY:WinMainCRTStartup /SUBSYSTEM:WINDOWS /OPT:REF /OPT:ICF /MANIFEST:EMBED ^
  /MANIFESTUAC:"level='asInvoker'" build\main.obj build\app.res ^
  kernel32.lib user32.lib gdi32.lib shell32.lib ole32.lib advapi32.lib comdlg32.lib d3d11.lib dxgi.lib windowscodecs.lib uuid.lib winhttp.lib bcrypt.lib ^
  /OUT:build\AuraSync.exe || exit /b 1
echo BUILD_OK
