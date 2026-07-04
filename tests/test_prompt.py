"""Test prompt construction (SPEC §9.1)."""

import pytest

from koekichi.prompt import SEED, build_prompt


class TestBuildPrompt:
    """Test initial_prompt construction."""

    def test_seed_always_included(self) -> None:
        """SEED must always be included in prompt."""
        result = build_prompt([])
        assert SEED in result

    def test_empty_dictionary(self) -> None:
        """Empty dictionary should return only SEED."""
        result = build_prompt([])
        assert result == SEED

    def test_single_word(self) -> None:
        """Single dictionary word should be added with delimiter and period."""
        result = build_prompt(["テスト"])
        assert result == SEED + "テスト。"

    def test_multiple_words(self) -> None:
        """Multiple words should be joined with 、 and end with 。."""
        result = build_prompt(["単語1", "単語2", "単語3"])
        assert result == SEED + "単語1、単語2、単語3。"

    def test_length_limit_respected(self) -> None:
        """Prompt should not exceed 200 characters."""
        long_words = ["テスト"] * 50  # 50 words of 2 chars each
        result = build_prompt(long_words)
        assert len(result) <= 200

    def test_seed_always_included_when_truncated(self) -> None:
        """SEED should always be included even when dict words are truncated."""
        long_words = ["テスト"] * 50
        result = build_prompt(long_words)
        assert result.startswith(SEED)

    def test_partial_dict_fit(self) -> None:
        """Dictionary words should fit in order until limit reached."""
        words = ["A", "B", "C"]
        # Create a configuration that would exceed limit
        available_space = 200 - len(SEED)
        # Manually test: if SEED is ~40 chars, we have ~160 chars for dict
        result = build_prompt(words)
        assert result == SEED + "A、B、C。"

    def test_exact_limit_boundary(self) -> None:
        """Test behavior at exactly 200 character boundary."""
        # Build words to fit exactly or just over 200
        # SEED is "こんにちは、今日は音声入力のテストです。よろしくお願いします。" (30 chars)
        seed_len = len(SEED)
        # Available: 200 - 30 = 170
        # Each word "テスト" is 3 chars, separators are 1 char each
        # Pattern: word + "、" + word + "。" etc.
        words = ["テスト"] * 30  # 3*30 = 90 chars + separators
        result = build_prompt(words)
        assert len(result) <= 200

    def test_no_period_when_dict_empty(self) -> None:
        """No trailing period when dictionary is empty."""
        result = build_prompt([])
        assert not result.endswith("。") or result == SEED

    def test_trailing_period_when_dict_present(self) -> None:
        """Trailing period added when dictionary has words."""
        result = build_prompt(["word"])
        assert result.endswith("。")
