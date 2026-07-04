"""Test antihallucination filters (SPEC §8 H3-H6)."""

import pytest

from koekichi.antihallucination import (
    filter_segments,
    normalize_for_match,
    should_reject_as_blacklist,
    should_reject_as_prompt_echo,
    should_reject_segment,
)
from koekichi.engine.base import Segment


class TestNormalizeForMatch:
    """Test normalize_for_match function."""

    def test_remove_whitespace(self) -> None:
        """Remove ASCII and full-width whitespace."""
        assert normalize_for_match("hello world") == "helloworld"
        assert normalize_for_match("こんにちは　世界") == "こんにちは世界"

    def test_remove_punctuation(self) -> None:
        """Remove punctuation marks."""
        text = "こんにちは、世界。テスト！？"
        result = normalize_for_match(text)
        assert "、" not in result
        assert "。" not in result
        assert "！" not in result
        assert "？" not in result

    def test_nfkc_normalization(self) -> None:
        """Apply NFKC normalization."""
        text = "Ｔｅｓｔ"  # Full-width
        result = normalize_for_match(text)
        assert result == "Test"  # Half-width after NFKC

    def test_halfwidth_punctuation_removed(self) -> None:
        """Half-width punctuation (｡ ｢ ｣) is removed via NFKC-first order."""
        text = "テスト｡｢かぎ｣"
        result = normalize_for_match(text)
        assert result == "テストかぎ"

    def test_fullwidth_comma_period_removed(self) -> None:
        """Full-width ，． removed even though NFKC folds them to , . first."""
        assert normalize_for_match("テスト，です．") == "テストです"


class TestSegmentRejection:
    """Test segment rejection criteria H3/H4."""

    def test_h3_high_no_speech_and_low_confidence(self) -> None:
        """H3: Reject if no_speech_prob > threshold AND avg_logprob < threshold."""
        segment = Segment(
            text="test",
            no_speech_prob=0.7,
            avg_logprob=-2.0,
        )
        assert should_reject_segment(
            segment,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )

    def test_h3_high_no_speech_only(self) -> None:
        """H3: Don't reject if only no_speech_prob is high."""
        segment = Segment(
            text="test",
            no_speech_prob=0.7,
            avg_logprob=0.0,  # High confidence
        )
        assert not should_reject_segment(
            segment,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )

    def test_h4_high_compression_ratio(self) -> None:
        """H4: Reject if compression_ratio > threshold."""
        segment = Segment(
            text="test",
            compression_ratio=2.5,
        )
        assert should_reject_segment(
            segment,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )

    def test_h4_normal_compression_ratio(self) -> None:
        """H4: Don't reject if compression_ratio is normal."""
        segment = Segment(
            text="test",
            compression_ratio=2.0,
        )
        assert not should_reject_segment(
            segment,
            no_speech_threshold=0.6,
            logprob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )


class TestBlacklist:
    """Test blacklist rejection (H5)."""

    def test_builtin_blacklist_exact_match(self) -> None:
        """H5: Reject if exact match to built-in blacklist."""
        assert should_reject_as_blacklist(
            "ご視聴ありがとうございました",
            [],
        )

    def test_builtin_blacklist_normalized_match(self) -> None:
        """H5: Match after normalization."""
        assert should_reject_as_blacklist(
            "ご視聴ありがとうございました。",  # Extra period
            [],
        )

    def test_builtin_blacklist_halfwidth_punct_match(self) -> None:
        """H5: Half-width period (｡) must not defeat blacklist matching."""
        assert should_reject_as_blacklist(
            "ご視聴ありがとうございました｡",  # Half-width period
            [],
        )

    def test_builtin_blacklist_no_partial_match(self) -> None:
        """H5: Don't reject on partial match."""
        assert not should_reject_as_blacklist(
            "ご視聴ありがとうございました、素晴らしい",
            [],
        )

    def test_extra_blacklist(self) -> None:
        """H5: Check user-provided extra blacklist."""
        assert should_reject_as_blacklist(
            "カスタムハルシネーション",
            ["カスタムハルシネーション"],
        )

    def test_all_builtin_entries(self) -> None:
        """H5: Verify all 6 built-in entries."""
        entries = [
            "ご視聴ありがとうございました",
            "ご清聴ありがとうございました",
            "チャンネル登録お願いします",
            "おやすみなさい",
            "最後までご視聴いただきありがとうございます",
            "字幕視聴ありがとうございました",
        ]
        for entry in entries:
            assert should_reject_as_blacklist(entry, [])


class TestPromptEcho:
    """Test prompt echo rejection (H6)."""

    def test_h6_exact_prompt_echo(self) -> None:
        """H6: Reject if segment is contained in prompt."""
        assert should_reject_as_prompt_echo(
            "こんにちは",
            "こんにちは、今日は音声入力のテストです。よろしくお願いします。",
        )

    def test_h6_not_in_prompt(self) -> None:
        """H6: Don't reject if segment not in prompt."""
        assert not should_reject_as_prompt_echo(
            "別の内容",
            "こんにちは、今日は音声入力のテストです。よろしくお願いします。",
        )

    def test_h6_prompt_echo_with_normalization(self) -> None:
        """H6: Match after normalization."""
        assert should_reject_as_prompt_echo(
            "こんにちは、",  # Extra punctuation
            "こんにちは、今日は音声入力のテストです。よろしくお願いします。",
        )


class TestFilterSegments:
    """Test full segment filtering pipeline."""

    def test_filter_keeps_good_segment(self) -> None:
        """Good segment should pass all checks."""
        segments = [
            Segment(
                text="良い認識結果",
                avg_logprob=-0.5,
                no_speech_prob=0.1,
                compression_ratio=1.5,
            )
        ]
        config = {
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
                "blacklist_extra": [],
            }
        }
        filtered = filter_segments(segments, config, "初期プロンプト")
        assert len(filtered) == 1

    def test_filter_rejects_h3_violation(self) -> None:
        """Segment violating H3 should be rejected."""
        segments = [
            Segment(
                text="test",
                avg_logprob=-2.0,
                no_speech_prob=0.8,
            )
        ]
        config = {
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
                "blacklist_extra": [],
            }
        }
        filtered = filter_segments(segments, config, "初期プロンプト")
        assert len(filtered) == 0

    def test_filter_rejects_blacklist(self) -> None:
        """Segment matching blacklist should be rejected."""
        segments = [
            Segment(
                text="ご視聴ありがとうございました",
                avg_logprob=-0.5,
                no_speech_prob=0.1,
            )
        ]
        config = {
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
                "blacklist_extra": [],
            }
        }
        filtered = filter_segments(segments, config, "初期プロンプト")
        assert len(filtered) == 0

    def test_filter_rejects_prompt_echo(self) -> None:
        """Segment that is prompt echo should be rejected."""
        initial_prompt = "こんにちは、今日は音声入力のテストです。よろしくお願いします。"
        segments = [
            Segment(
                text="こんにちは",
                avg_logprob=-0.5,
                no_speech_prob=0.1,
            )
        ]
        config = {
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
                "blacklist_extra": [],
            }
        }
        filtered = filter_segments(segments, config, initial_prompt)
        assert len(filtered) == 0
