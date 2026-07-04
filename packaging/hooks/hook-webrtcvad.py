# Override for pyinstaller-hooks-contrib's built-in hook-webrtcvad.py.
#
# That hook does `copy_metadata('webrtcvad')`, assuming the installed
# distribution is named "webrtcvad". This project depends on
# "webrtcvad-wheels" instead (see pyproject.toml), which provides the same
# `webrtcvad` importable module but is registered under a different
# distribution name — so copy_metadata('webrtcvad') raises
# PackageNotFoundError and aborts the whole PyInstaller build.
#
# koekichi does not rely on webrtcvad's package metadata at runtime (no
# importlib.metadata.version() calls on it), so it is safe to provide no
# metadata here. This hookspath entry (packaging/hooks/) is listed before
# PyInstaller's contrib hooks in Analysis(), so it takes precedence.

datas = []
