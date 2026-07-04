# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: macOS build (SPEC §18.3, §18.4).

Build with:
    uv run pyinstaller packaging/koekichi-mac.spec --noconfirm

Produces dist/KoeKichi.app (onedir COLLECT wrapped in a BUNDLE). arm64 only;
this is not a cross-build spec (SPEC §18.4: "arm64 専用").
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# SPECPATH is injected by PyInstaller into this file's globals.
ROOT = Path(SPECPATH).resolve().parent  # packaging/ -> project root
sys.path.insert(0, str(ROOT))

from koekichi import __version__  # noqa: E402

# --- SPEC §18.3: explicit collect_all for packages with compiled extensions
# or data assets (mel filters, tokenizers, Silero VAD weights, Metal shaders)
# that PyInstaller's automatic import analysis would otherwise miss. ---
datas: list = []
binaries: list = []
hiddenimports: list = []

for _pkg in (
    "mlx",  # Metal shader library (mlx.metallib) — mac spec only
    "mlx_whisper",  # mel filters, tokenizer assets
    "faster_whisper",  # Silero VAD assets etc.
    "ctranslate2",
    "onnxruntime",
    "webrtcvad",
):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

hiddenimports += ["koekichi"]

# collect_all('mlx') can miss the Metal shader library depending on how the
# wheel lays out binaries vs. package data; add it explicitly as a fallback
# (SPEC note: this avoids a runtime "unable to load mlx.metallib" error).
try:
    import mlx

    _metallib = Path(mlx.__path__[0]) / "lib" / "mlx.metallib"
    if _metallib.exists() and not any(Path(d[1]) == Path("mlx/lib") for d in datas):
        datas.append((str(_metallib), "mlx/lib"))
except ImportError:
    pass

# --- SPEC §18.3: exclude unused Qt modules and other large unused packages
# to keep bundle size down. PySide6/sounddevice/pynput otherwise rely on
# PyInstaller's standard hooks. ---
excludes = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtSensors",
    "PySide6.QtPositioning",
    "PySide6.QtNfc",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "tkinter",
    "matplotlib",
    # NOTE: do not exclude "unittest"/"test" — numpy/scipy's lazy submodule
    # loading (numpy.testing, scipy._lib._array_api) imports `unittest` at
    # runtime even in normal (non-test) use; excluding it breaks mlx_whisper
    # import with "No module named 'unittest'".
]

icon_path = ROOT / "packaging" / "icon.icns"

block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # packaging/hooks/hook-webrtcvad.py overrides pyinstaller-hooks-contrib's
    # broken hook (see that file's docstring for why).
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KoeKichi",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # windowed (SPEC §18.3)
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="KoeKichi",
)

app = BUNDLE(
    coll,
    name="KoeKichi.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="jp.koekichi.app",
    info_plist={
        # SPEC §18.4
        "CFBundleIdentifier": "jp.koekichi.app",
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "LSUIElement": True,  # menu-bar-only app, no Dock icon
        "NSMicrophoneUsageDescription": "音声入力のためにマイクを使用します。",
        "LSMinimumSystemVersion": "13.0",
    },
)
