"""Test configuration loading and merging (SPEC §5)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from koekichi.config import (
    DEFAULT_CONFIG,
    _deep_merge,
    get_nested,
    load_config,
    save_config,
)


class TestDeepMerge:
    """Test deep dictionary merging."""

    def test_merge_empty_into_base(self) -> None:
        """Merging empty dict should keep base."""
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {})
        assert result == base

    def test_merge_flat_dicts(self) -> None:
        """Merge flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self) -> None:
        """Merge nested dictionaries recursively."""
        base = {"engine": {"backend": "auto", "model": "small"}}
        override = {"engine": {"backend": "faster-whisper"}}
        result = _deep_merge(base, override)
        assert result == {
            "engine": {"backend": "faster-whisper", "model": "small"}
        }

    def test_merge_deep_nesting(self) -> None:
        """Merge deeply nested dictionaries."""
        base = {
            "format": {
                "llm": {"enabled": False, "endpoint": "http://127.0.0.1:11434"}
            }
        }
        override = {"format": {"llm": {"enabled": True}}}
        result = _deep_merge(base, override)
        assert result["format"]["llm"]["enabled"] is True
        assert result["format"]["llm"]["endpoint"] == "http://127.0.0.1:11434"

    def test_override_non_dict_with_dict(self) -> None:
        """Override non-dict value with dict."""
        base = {"a": 1}
        override = {"a": {"b": 2}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": 2}}

    def test_override_dict_with_non_dict(self) -> None:
        """Override dict value with non-dict."""
        base = {"a": {"b": 2}}
        override = {"a": 1}
        result = _deep_merge(base, override)
        assert result == {"a": 1}


class TestGetNested:
    """Test nested config value retrieval."""

    def test_get_top_level(self) -> None:
        """Get top-level key."""
        cfg = {"language": "ja"}
        result = get_nested(cfg, "language")
        assert result == "ja"

    def test_get_nested_key(self) -> None:
        """Get nested key with dot notation."""
        cfg = {"engine": {"backend": "auto"}}
        result = get_nested(cfg, "engine.backend")
        assert result == "auto"

    def test_get_deeply_nested(self) -> None:
        """Get deeply nested key."""
        cfg = {"format": {"llm": {"enabled": False}}}
        result = get_nested(cfg, "format.llm.enabled")
        assert result is False

    def test_get_missing_key_returns_default(self) -> None:
        """Missing key returns default value."""
        cfg = {"language": "ja"}
        result = get_nested(cfg, "engine.backend", "default_value")
        assert result == "default_value"

    def test_get_missing_nested_returns_default(self) -> None:
        """Missing nested key returns default."""
        cfg = {"engine": {}}
        result = get_nested(cfg, "engine.backend", "fallback")
        assert result == "fallback"


class TestConfigDefaults:
    """Test default configuration structure."""

    def test_default_config_has_required_keys(self) -> None:
        """Default config has all required top-level keys."""
        required_keys = [
            "language",
            "engine",
            "hotkey",
            "audio",
            "vad",
            "format",
            "insert",
            "ui",
            "hallucination",
            "log_level",
        ]
        for key in required_keys:
            assert key in DEFAULT_CONFIG

    def test_engine_config_defaults(self) -> None:
        """Engine config has expected defaults."""
        engine_cfg = DEFAULT_CONFIG["engine"]
        assert engine_cfg["backend"] == "auto"
        assert engine_cfg["model"] == "auto"
        assert engine_cfg["beam_size"] == 1

    def test_vad_config_defaults(self) -> None:
        """VAD config has expected defaults."""
        vad_cfg = DEFAULT_CONFIG["vad"]
        assert vad_cfg["aggressiveness"] == 2
        assert vad_cfg["min_speech_ms"] == 300
        assert vad_cfg["pad_ms"] == 200


class TestConfigMerging:
    """Test configuration merging behavior."""

    def test_merge_with_defaults_fills_missing_keys(self) -> None:
        """Merging fills in missing keys from defaults."""
        # Simulate partial config
        partial = {"language": "en"}
        merged = _deep_merge(DEFAULT_CONFIG.copy(), partial)
        # Should have all default keys
        assert merged["engine"]["backend"] == "auto"
        assert merged["language"] == "en"

    def test_merge_preserves_unspecified_engine_config(self) -> None:
        """Engine config values not in override are preserved."""
        partial = {"engine": {"backend": "mlx"}}
        merged = _deep_merge(DEFAULT_CONFIG.copy(), partial)
        assert merged["engine"]["backend"] == "mlx"
        assert merged["engine"]["beam_size"] == 1  # From defaults

    def test_nested_list_not_merged(self) -> None:
        """Lists are replaced, not merged."""
        base = {"hallucination": {"blacklist_extra": ["a", "b"]}}
        override = {"hallucination": {"blacklist_extra": ["c"]}}
        result = _deep_merge(base, override)
        assert result["hallucination"]["blacklist_extra"] == ["c"]


class TestConfigDeepCopy:
    """Test SPEC §5: load_config returns deep copy, not shared references."""

    def test_load_config_returns_independent_engine_dict(self) -> None:
        """load_config() should return a deep copy; engine dict must be independent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            # No config file exists, so load_config will create defaults
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg = load_config()

            # Modify the returned config's engine dict
            cfg["engine"]["backend"] = "modified"

            # Load again
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg2 = load_config()

            # cfg2's engine should still have the default value
            assert cfg2["engine"]["backend"] == "auto"

            # And DEFAULT_CONFIG should also still have default
            assert DEFAULT_CONFIG["engine"]["backend"] == "auto"

    def test_load_config_does_not_share_hotkey_dict(self) -> None:
        """Hotkey dict in load_config() result must be independent from DEFAULT_CONFIG."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg = load_config()

            # Modify hotkey config in returned dict
            cfg["hotkey"]["mode"] = "modified"

            # Load again
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg2 = load_config()

            # cfg2's hotkey should still have default
            assert cfg2["hotkey"]["mode"] == "toggle"

    def test_returned_config_dicts_are_different_objects(self) -> None:
        """Each load_config() call should return different dict objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg1 = load_config()
                cfg2 = load_config()

            # Different top-level dicts
            assert cfg1 is not cfg2

            # Different nested dicts
            assert cfg1["engine"] is not cfg2["engine"]
            assert cfg1["hotkey"] is not cfg2["hotkey"]
            assert cfg1["audio"] is not cfg2["audio"]

            # But values should be equal
            assert cfg1 == cfg2

    def test_load_config_from_file_creates_deep_copy(self) -> None:
        """load_config() with existing file should return deep copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.json"
            # Create a partial config file
            partial_config = {"language": "en", "engine": {"backend": "mlx"}}
            with open(config_file, "w") as f:
                json.dump(partial_config, f)

            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg = load_config()

            # Modify returned config
            cfg["engine"]["backend"] = "modified"
            cfg["audio"]["sample_rate"] = 8000

            # Load again and verify defaults are preserved
            with patch("koekichi.config.get_config_file", return_value=config_file):
                cfg2 = load_config()

            assert cfg2["engine"]["backend"] == "mlx"  # From file
            assert cfg2["audio"]["sample_rate"] == 16000  # From defaults
            assert DEFAULT_CONFIG["audio"]["sample_rate"] == 16000
