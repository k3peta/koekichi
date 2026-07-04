@echo off
REM Build KoeKichi\KoeKichi.exe for Windows (SPEC §18.5).
REM Run from the project root, or this script will cd there itself.
REM Must be run on a Windows machine (this repo's Mac dev environment
REM cannot cross-build a Windows PyInstaller bundle; see BUILD.md).

setlocal
cd /d "%~dp0\.."

echo ==^> uv sync
uv sync
if errorlevel 1 goto :error

if not exist "packaging\icon.ico" (
    echo ==^> Generating icons ^(packaging\make_icons.py^)
    uv run python packaging\make_icons.py
    if errorlevel 1 goto :error
)

echo ==^> Cleaning previous build output
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo ==^> Running PyInstaller
uv run pyinstaller packaging\koekichi-win.spec --noconfirm
if errorlevel 1 goto :error

echo ==^> Build complete: dist\KoeKichi\KoeKichi.exe
echo ==^> Next: compile packaging\koekichi.iss with Inno Setup 6 to produce the installer.
goto :eof

:error
echo Build failed.
exit /b 1
