"""Test LLM formatting with content-preservation guard (SPEC §9.3)."""

from unittest.mock import MagicMock, patch

import pytest

from koekichi.llm_format import format_with_llm, SYSTEM_PROMPT


class TestLLMFormatting:
    """Test LLM-based text formatting."""

    def test_llm_disabled_returns_unchanged(self) -> None:
        """Disabled LLM should return text unchanged."""
        text = "テスト"
        config = {"format": {"llm": {"enabled": False}}}
        result = format_with_llm(text, config)
        assert result == text

    def test_llm_enabled_with_mock(self) -> None:
        """With LLM enabled, should POST to Ollama endpoint."""
        text = "これはテストです"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "これはテストです。"}
            }
            mock_post.return_value = mock_response

            result = format_with_llm(text, config)
            assert result == "これはテストです。"
            mock_post.assert_called_once()

    def test_llm_content_preservation_guard_rejects_modification(self) -> None:
        """LLM output that changes content should be rejected."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            # LLM returns modified content (word added)
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": "テスト別の内容"}
            }
            mock_post.return_value = mock_response

            result = format_with_llm(text, config)
            # Should return original because content changed
            assert result == text

    def test_llm_timeout_fallback(self) -> None:
        """Timeout should fall back to original."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            import requests
            mock_post.side_effect = requests.exceptions.Timeout()

            result = format_with_llm(text, config)
            assert result == text

    def test_llm_connection_error_fallback(self) -> None:
        """Connection error should fall back to original."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            import requests
            mock_post.side_effect = requests.exceptions.ConnectionError()

            result = format_with_llm(text, config)
            assert result == text

    def test_llm_http_error_fallback(self) -> None:
        """HTTP error should fall back to original."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            import requests
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
            mock_post.return_value = mock_response

            result = format_with_llm(text, config)
            assert result == text

    def test_llm_empty_response_fallback(self) -> None:
        """Empty LLM response should fall back to original."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"message": {"content": ""}}
            mock_post.return_value = mock_response

            result = format_with_llm(text, config)
            assert result == text

    def test_llm_normalization_match(self) -> None:
        """Content guard uses normalize_for_match, allowing punctuation changes."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        with patch("requests.post") as mock_post:
            # LLM adds punctuation (allowed by normalize_for_match)
            mock_response = MagicMock()
            mock_response.json.return_value = {"message": {"content": "テスト。"}}
            mock_post.return_value = mock_response

            result = format_with_llm(text, config)
            # Should accept because punctuation doesn't change normalized content
            assert result == "テスト。"

    def test_requests_import_failure_handled(self) -> None:
        """Gracefully handle requests import failure."""
        text = "テスト"
        config = {
            "format": {
                "llm": {
                    "enabled": True,
                    "endpoint": "http://127.0.0.1:11434",
                    "model": "qwen2.5:3b-instruct",
                    "timeout_s": 6,
                }
            }
        }

        # Mock the sys.modules to make requests unimportable
        import sys
        old_requests = sys.modules.get('requests')
        try:
            sys.modules['requests'] = None
            result = format_with_llm(text, config)
            assert result == text
        finally:
            if old_requests is None:
                sys.modules.pop('requests', None)
            else:
                sys.modules['requests'] = old_requests
