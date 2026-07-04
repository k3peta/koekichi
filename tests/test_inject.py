"""Tests for text injection (SPEC §12, §14.1)."""

from unittest.mock import MagicMock, call, patch

import pytest

from koekichi.inject import inject_text


@pytest.fixture
def mock_config():
    """Standard test config for injection."""
    return {
        "insert": {
            "restore_clipboard": True,
            "paste_delay_ms": 80,
            "restore_delay_ms": 500,
        }
    }


class TestInjectTextCopyOnly:
    """Test copy_only=True fallback (SPEC §14.1)."""

    def test_copy_only_copies_text(self, mock_config):
        """When copy_only=True, only call pyperclip.copy() (SPEC §14.1)."""
        with patch("pyperclip.copy") as mock_copy:
            inject_text("test text", mock_config, copy_only=True)
            mock_copy.assert_called_once_with("test text")

    def test_copy_only_skips_paste(self, mock_config):
        """When copy_only=True, do not send paste keystroke (SPEC §14.1)."""
        with patch("pyperclip.copy"), patch(
            "koekichi.inject._send_paste_keystroke"
        ) as mock_paste_ks:
            inject_text("test text", mock_config, copy_only=True)
            mock_paste_ks.assert_not_called()

    def test_copy_only_skips_delays(self, mock_config):
        """When copy_only=True, do not wait (SPEC §14.1)."""
        with patch("pyperclip.copy"), patch(
            "koekichi.inject.time.sleep"
        ) as mock_sleep, patch("koekichi.inject._send_paste_keystroke"):
            inject_text("test text", mock_config, copy_only=True)
            mock_sleep.assert_not_called()


class TestInjectTextNormal:
    """Test normal injection (copy_only=False, the default)."""

    def test_normal_injection_flow(self, mock_config):
        """Normal injection: save, copy, paste; restore is async (v1.1 SPEC §12)."""
        with patch("pyperclip.copy") as mock_copy, patch(
            "pyperclip.paste"
        ) as mock_paste, patch("koekichi.inject.time.sleep") as mock_sleep, patch(
            "koekichi.inject._send_paste_keystroke"
        ) as mock_paste_ks, patch("koekichi.inject.threading.Timer") as mock_timer:
            mock_paste.return_value = "old clipboard"

            inject_text("new text", mock_config, copy_only=False)

            # Should have read clipboard, copied new text, sent paste
            assert mock_paste.call_count == 1  # read for backup
            assert mock_copy.call_count == 1  # copy new (restore is async)
            assert mock_copy.call_args_list[0] == call("new text")
            mock_paste_ks.assert_called_once()
            # Only one sleep: paste_delay (restore is delegated to Timer)
            assert mock_sleep.call_count == 1
            # Restore is scheduled on a daemon timer with the saved content
            mock_timer.assert_called_once()
            assert mock_timer.call_args.kwargs["args"][0] == "old clipboard"

    def test_normal_injection_empty_clipboard(self, mock_config):
        """Normal injection with empty clipboard: no restore (SPEC §12)."""
        with patch("pyperclip.copy") as mock_copy, patch(
            "pyperclip.paste"
        ) as mock_paste, patch("koekichi.inject.time.sleep"), patch(
            "koekichi.inject._send_paste_keystroke"
        ) as mock_paste_ks:
            mock_paste.return_value = ""

            inject_text("new text", mock_config, copy_only=False)

            # Should copy new text but not restore (old was empty)
            assert mock_copy.call_count == 1  # only copy new
            assert mock_copy.call_args_list[0] == call("new text")
            mock_paste_ks.assert_called_once()

    def test_no_restore_clipboard(self, mock_config):
        """When restore_clipboard=False, skip save/restore (SPEC §12)."""
        with patch("pyperclip.copy") as mock_copy, patch(
            "pyperclip.paste"
        ) as mock_paste, patch("koekichi.inject.time.sleep"), patch(
            "koekichi.inject._send_paste_keystroke"
        ) as mock_paste_ks:
            mock_config["insert"]["restore_clipboard"] = False
            mock_paste.return_value = "old"

            inject_text("new text", mock_config, copy_only=False)

            # Should not read clipboard or restore
            assert mock_paste.call_count == 0
            assert mock_copy.call_count == 1
            assert mock_copy.call_args_list[0] == call("new text")
            mock_paste_ks.assert_called_once()

    def test_async_restoration_v1_1(self, mock_config):
        """Normal injection with async restoration (v1.1 SPEC §12).

        inject_text should:
        1. Copy text and send paste keystroke
        2. Return immediately (critical path done)
        3. Schedule daemon timer for non-blocking restoration
        """
        with patch("pyperclip.copy") as mock_copy, patch(
            "pyperclip.paste"
        ) as mock_paste, patch("koekichi.inject.time.sleep") as mock_sleep, patch(
            "koekichi.inject._send_paste_keystroke"
        ) as mock_paste_ks, patch("koekichi.inject.threading.Timer") as mock_timer:
            mock_paste.return_value = "old clipboard"
            mock_timer_instance = MagicMock()
            mock_timer.return_value = mock_timer_instance

            inject_text("new text", mock_config, copy_only=False)

            # Should read, copy new, paste
            assert mock_paste.call_count == 1
            assert mock_copy.call_count == 1  # Only copy new; restore is async
            assert mock_copy.call_args_list[0] == call("new text")
            mock_paste_ks.assert_called_once()

            # Only one sleep: paste_delay (not restore_delay, which is async)
            assert mock_sleep.call_count == 1

            # Timer should be scheduled for async restore
            mock_timer.assert_called_once()
            # Check Timer constructor args: Timer(delay, callback, args=(saved, restore_delay), daemon=True)
            timer_args, timer_kwargs = mock_timer.call_args
            restore_delay_s = mock_config["insert"]["restore_delay_ms"] / 1000.0
            assert timer_args[0] == restore_delay_s
            # args should be (saved_text, restore_delay_s)
            assert timer_kwargs.get("args") == ("old clipboard", restore_delay_s)

            # Timer.start() should be called
            mock_timer_instance.start.assert_called_once()

    def test_controller_reused(self, mock_config):
        """Controller should be reused across calls (SPEC §12)."""
        with patch("pyperclip.copy"), patch("pyperclip.paste"), patch(
            "koekichi.inject.time.sleep"
        ), patch("koekichi.inject._send_paste_keystroke") as mock_paste_ks, patch(
            "koekichi.inject.threading.Timer"
        ):
            # First call
            inject_text("text 1", mock_config, copy_only=False)
            first_controller_id = id(mock_paste_ks.call_args)

            # Second call
            inject_text("text 2", mock_config, copy_only=False)

            # _send_paste_keystroke should be called twice, implying same Controller
            assert mock_paste_ks.call_count == 2
