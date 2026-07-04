"""Tests for macOS permission self-checks (SPEC §14.1)."""

import sys

import pytest

from koekichi.macos_perms import accessibility_trusted, input_monitoring_granted


class TestAccessibilityTrusted:
    """Test accessibility_trusted() function."""

    def test_non_darwin_always_true(self, monkeypatch):
        """Non-darwin platforms always return True (SPEC §14.1)."""
        monkeypatch.setattr(sys, "platform", "linux")
        assert accessibility_trusted() is True

    def test_darwin_returns_bool(self, monkeypatch):
        """On darwin, returns a bool (value depends on system state)."""
        # Only run on actual darwin; skip on other platforms
        if sys.platform != "darwin":
            pytest.skip("darwin-only test")
        result = accessibility_trusted()
        assert isinstance(result, bool)


class TestInputMonitoringGranted:
    """Test input_monitoring_granted() function."""

    def test_non_darwin_always_true(self, monkeypatch):
        """Non-darwin platforms always return True (SPEC §14.1)."""
        monkeypatch.setattr(sys, "platform", "linux")
        assert input_monitoring_granted() is True

    def test_darwin_returns_bool(self):
        """On darwin, returns a bool (value depends on system state)."""
        # Only run on actual darwin; skip on other platforms
        if sys.platform != "darwin":
            pytest.skip("darwin-only test")
        result = input_monitoring_granted()
        assert isinstance(result, bool)
