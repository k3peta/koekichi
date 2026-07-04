"""Test config dir resolution and first-run setup marker (SPEC §11.4, §18.7)."""

import koekichi.paths as paths_module
from koekichi.paths import (
    is_setup_done,
    setup_marker_file,
    write_setup_marker,
)


class TestSetupMarker:
    """Test setup_done marker file判定 (first-run wizard gating)."""

    def test_not_done_when_config_dir_missing(self, tmp_path, monkeypatch) -> None:
        """A brand-new config dir (not even created yet) means not done."""
        missing_dir = tmp_path / "does-not-exist-yet"
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: missing_dir)
        assert is_setup_done() is False

    def test_not_done_when_marker_absent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: tmp_path)
        assert is_setup_done() is False

    def test_done_after_writing_marker(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: tmp_path)
        write_setup_marker("1.0.0")
        assert is_setup_done() is True

    def test_marker_content_is_version_string(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: tmp_path)
        write_setup_marker("1.2.3")
        marker = setup_marker_file()
        assert marker.exists()
        assert marker.read_text(encoding="utf-8") == "1.2.3"

    def test_write_setup_marker_creates_config_dir(self, tmp_path, monkeypatch) -> None:
        """write_setup_marker must create the config dir if missing (mkdir -p)."""
        missing_dir = tmp_path / "nested" / "koekichi-config"
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: missing_dir)
        write_setup_marker("1.0.0")
        assert missing_dir.exists()
        assert is_setup_done() is True

    def test_write_setup_marker_does_not_raise_on_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        """Failures (e.g. unwritable path) are logged, not raised."""
        # Point at a path whose parent is actually a file, so mkdir fails.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        bogus_dir = blocker / "config"
        monkeypatch.setattr(paths_module, "get_config_dir", lambda: bogus_dir)
        write_setup_marker("1.0.0")  # must not raise
