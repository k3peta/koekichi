"""OS-specific configuration directory resolution."""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_config_dir() -> Path:
    """
    Return the OS-specific configuration directory for KoeKichi.

    - macOS: ~/Library/Application Support/KoeKichi
    - Windows: %APPDATA%/KoeKichi
    - Other: ~/.koekichi

    Returns:
        Path: Resolved configuration directory (not necessarily existing)
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "KoeKichi"
    elif sys.platform == "win32":
        appdata_env = os.environ.get("APPDATA")
        if appdata_env:
            appdata = Path(appdata_env)
        else:
            appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "KoeKichi"
    else:
        # Unix-like systems
        return Path.home() / ".koekichi"


def ensure_config_dir() -> Path:
    """
    Ensure the configuration directory exists, creating it if necessary.

    Returns:
        Path: The configuration directory
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def setup_marker_file() -> Path:
    """
    Path to the first-run setup marker file (SPEC §11.4).

    Its presence indicates the first-run wizard has already been shown
    (successfully completed or dismissed). Content is the app version
    string that wrote it.

    Returns:
        Path: The marker file path (not necessarily existing)
    """
    return get_config_dir() / "setup_done"


def is_setup_done() -> bool:
    """
    Return True if the first-run setup wizard has already been shown.

    Returns:
        bool: True if the setup_done marker file exists
    """
    return setup_marker_file().exists()


def write_setup_marker(version: str) -> None:
    """
    Write the setup_done marker file, recording the app version.

    Args:
        version: App version string to store as the marker content
    """
    try:
        marker = ensure_config_dir() / "setup_done"
        marker.write_text(version, encoding="utf-8")
        logger.info(f"Wrote setup marker: {marker}")
    except Exception as e:
        logger.error(f"Failed to write setup marker: {e}")
