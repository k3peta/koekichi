# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Windows build (SPEC §18.3, §18.5).

Build with (on Windows, in an `uv sync`-ed environment):
    uv run pyinstaller packaging\\koekichi-win.spec --noconfirm

Produces dist\\KoeKichi\\KoeKichi.exe (onedir, no BUNDLE step — that is
macOS-only). This spec deliberately does NOT include mlx / mlx_whisper:
mlx is Apple Silicon (Metal) only and is never installed on Windows
(SPEC §4, §18.5).
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent  # packaging/ -> project root
sys.path.insert(0, str(ROOT))

from koekichi import __version__  # noqa: E402, F401

# --- SPEC §18.3: explicit collect_all for packages with compiled extensions
# or data assets that PyInstaller's automatic import analysis would miss. ---
datas: list = []
binaries: list = []
hiddenimports: list = []

for _pkg in (
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

# --- SPEC §18.3/§18.5: exclude unused Qt modules, other large unused
# packages, and mlx (mac-only backend, not installed on Windows anyway). ---
excludes = [
    "mlx",
    "mlx_whisper",
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

icon_path = ROOT / "packaging" / "icon.ico"

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
