"""Configuration loading, merging, and validation."""

import copy
import json
import logging
from pathlib import Path
from typing import Any

from koekichi.paths import ensure_config_dir

logger = logging.getLogger(__name__)


# SPEC §5: Default configuration schema
DEFAULT_CONFIG = {
    "language": "ja",
    "engine": {
        "backend": "auto",
        "model": "auto",
        "device": "auto",
        "compute_type": "int8",
        "beam_size": 1,
        "cpu_threads": 0,
    },
    "hotkey": {
        "type": "double-tap",
        "double_tap_key": "alt",
        "double_tap_window_ms": 400,
        "hold_to_record": True,
        "hold_threshold_ms": 300,
        "mode": "toggle",
        "combo": "<ctrl>+<shift>+<space>",
    },
    "audio": {
        "device": None,
        "sample_rate": 16000,
        "max_duration_s": 120,
        "idle_stream": "running",
        "pre_roll_ms": 200,
    },
    "vad": {
        "aggressiveness": 2,
        "min_speech_ms": 300,
        "pad_ms": 200,
        "min_speech_ratio": 0.10,
    },
    "format": {
        "rules_enabled": True,
        "normalize_ja_punct": True,
        "ensure_final_period": False,
        "llm": {
            "enabled": False,
            "endpoint": "http://127.0.0.1:11434",
            "model": "qwen2.5:3b-instruct",
            "timeout_s": 6,
        },
    },
    "insert": {
        "method": "clipboard",
        "restore_clipboard": True,
        "paste_delay_ms": 30,
        "restore_delay_ms": 500,
    },
    "ui": {
        "overlay": True,
        "overlay_position": "bottom-center",
    },
    "hallucination": {
        "no_speech_threshold": 0.6,
        "logprob_threshold": -1.0,
        "compression_ratio_threshold": 2.4,
        "blacklist_extra": [],
    },
    "log_level": "INFO",
}


def get_config_file() -> Path:
    """Get the path to config.json."""
    return ensure_config_dir() / "config.json"


def load_config() -> dict[str, Any]:
    """
    Load configuration from config.json.

    - If file doesn't exist, create it with defaults and return defaults.
    - If file exists, merge with defaults (missing keys filled from defaults).
    - Unknown keys (in loaded config) logged as warnings but not removed.
    - JSON parse errors: Log error and return defaults without overwriting file.

    Returns:
        dict: Merged configuration (deeply copied, independent from DEFAULT_CONFIG)

    SPEC §5: Returns must be a deep copy to avoid polluting DEFAULT_CONFIG.
    """
    config_file = get_config_file()

    if not config_file.exists():
        # Create default config (SPEC §5: must be deep copy)
        save_config(copy.deepcopy(DEFAULT_CONFIG))
        logger.info(f"Created default config at {config_file}")
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse config.json: {e}. Using defaults.")
        return copy.deepcopy(DEFAULT_CONFIG)
    except Exception as e:
        logger.error(f"Failed to read config.json: {e}. Using defaults.")
        return copy.deepcopy(DEFAULT_CONFIG)

    # Merge: recursive deep merge of loaded into defaults (SPEC §5: deep copy base)
    merged = _deep_merge(copy.deepcopy(DEFAULT_CONFIG), loaded)

    # Check for unknown keys at top level
    for key in loaded:
        if key not in DEFAULT_CONFIG:
            logger.warning(f"Unknown top-level config key: {key}")

    # Check for unknown keys in nested dicts (simple one level)
    for section, section_defaults in DEFAULT_CONFIG.items():
        if isinstance(section_defaults, dict) and section in loaded:
            if isinstance(loaded[section], dict):
                for key in loaded[section]:
                    if key not in section_defaults:
                        logger.warning(f"Unknown config key in section '{section}': {key}")

    return merged


def save_config(cfg: dict[str, Any]) -> None:
    """
    Save configuration to config.json.

    Args:
        cfg: Configuration dictionary to save
    """
    config_file = get_config_file()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved config to {config_file}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge override dict into base dict.

    Dicts are merged recursively; other values from override replace base.

    Args:
        base: Base configuration
        override: Configuration to merge in

    Returns:
        dict: Merged result
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_nested(cfg: dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Get a nested config value by dot-separated path.

    Args:
        cfg: Configuration dict
        path: Dot-separated path (e.g. "engine.backend")
        default: Default value if path not found

    Returns:
        The value at the path, or default
    """
    parts = path.split(".")
    current = cfg
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
            if current is None:
                return default
        else:
            return default
    return current
