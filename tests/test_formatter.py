"""Test formatter rules F1-F6 (SPEC §9.2, table-driven, minimum 15 cases)."""

import pytest

from koekichi.formatter import format_text


class TestFormatterTableDriven:
    """Table-driven tests for formatter rules F1-F6."""

    @pytest.mark.parametrize(
        "text,config,expected",
        [
            # F1: Basic whitespace stripping
            ("  hello world  ", {"language": "ja", "format": {"rules_enabled": True}}, "hello world"),

            # F2: Japanese punctuation normalization (，→、, ．→。)
            (
                "これは，テストです．",
                {"language": "ja", "format": {"rules_enabled": True, "normalize_ja_punct": True}},
                "これは、テストです。",
            ),

            # F2: Disable normalize_ja_punct
            (
                "これは，テストです．",
                {"language": "ja", "format": {"rules_enabled": True, "normalize_ja_punct": False}},
                "これは，テストです．",
            ),

            # F3: Compress consecutive periods
            ("です。。。", {"language": "ja", "format": {"rules_enabled": True}}, "です。"),

            # F3: Compress consecutive reading marks
            ("です、、、", {"language": "ja", "format": {"rules_enabled": True}}, "です、"),

            # F4: Replace 、。 with 。
            ("です、。", {"language": "ja", "format": {"rules_enabled": True}}, "です。"),

            # F5: Remove space before punctuation
            ("です 。", {"language": "ja", "format": {"rules_enabled": True}}, "です。"),

            # F5: Remove space after punctuation (ja)
            ("です。 次", {"language": "ja", "format": {"rules_enabled": True}}, "です。次"),

            # F6: Ensure final period when enabled
            (
                "これはテスト",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "これはテスト。",
            ),

            # F6: Don't add period when already ends with punctuation
            (
                "これはテスト。",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "これはテスト。",
            ),

            # F6: Don't add if disabled
            (
                "これはテスト",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": False}},
                "これはテスト",
            ),

            # F6: Already ends with question mark
            (
                "テスト？",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "テスト？",
            ),

            # F6: Already ends with exclamation mark
            (
                "テスト！",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "テスト！",
            ),

            # Rules disabled
            (
                "  です  。。  ",
                {"language": "ja", "format": {"rules_enabled": False}},
                "  です  。。  ",
            ),

            # Complex case: multiple rules applied in order
            (
                "  です、。  次です  ．  ",
                {"language": "ja", "format": {"rules_enabled": True, "normalize_ja_punct": True}},
                "です。次です。",
            ),

            # F5: Multiple spaces after punctuation
            (
                "です。   次",
                {"language": "ja", "format": {"rules_enabled": True}},
                "です。次",
            ),

            # Half-width and full-width mixed
            (
                "テスト　です。",
                {"language": "ja", "format": {"rules_enabled": True}},
                "テスト　です。",
            ),

            # Ends with closing bracket
            (
                "テスト」",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "テスト」",
            ),

            # Ends with ellipsis
            (
                "テスト…",
                {"language": "ja", "format": {"rules_enabled": True, "ensure_final_period": True}},
                "テスト…",
            ),
        ],
    )
    def test_format_text(self, text: str, config: dict, expected: str) -> None:
        """Test format_text with various inputs and rules."""
        result = format_text(text, config)
        assert result == expected, f"Expected '{expected}', got '{result}'"
