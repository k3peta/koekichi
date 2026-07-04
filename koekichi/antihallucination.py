"""Hallucination filtering (SPEC §8 H3-H6)."""

import re
import unicodedata
from typing import Any

from koekichi.engine.base import Segment


# SPEC §8 H5: Built-in blacklist (6 sentences minimum)
BUILTIN_BLACKLIST = [
    "ご視聴ありがとうございました",
    "ご清聴ありがとうございました",
    "チャンネル登録お願いします",
    "おやすみなさい",
    "最後までご視聴いただきありがとうございます",
    "字幕視聴ありがとうございました",
]


def normalize_for_match(s: str) -> str:
    """
    Normalize text for matching (SPEC §8 H5/H6).

    Order (SPEC §8): NFKC normalization first, then remove whitespace,
    then remove punctuation marks (、。，．！？!?…「」). NFKC-first ensures
    half-width variants (e.g. ｡ ｢ ｣) are folded to full-width forms and
    stripped by the punctuation pass.

    Args:
        s: String to normalize

    Returns:
        str: Normalized string
    """
    # Apply NFKC normalization first
    s = unicodedata.normalize("NFKC", s)

    # Remove ASCII and full-width whitespace
    s = re.sub(r"[\s　]+", "", s)

    # Remove punctuation and bracket marks
    # 、。，．！？!?…「」 (plus half-width , . since NFKC folds ，．into them)
    punctuation_to_remove = "、。，．！？!?…「」,."
    for char in punctuation_to_remove:
        s = s.replace(char, "")

    return s


def should_reject_segment(
    segment: Segment,
    no_speech_threshold: float,
    logprob_threshold: float,
    compression_ratio_threshold: float,
) -> bool:
    """
    Check if segment should be rejected (SPEC §8 H3/H4).

    H3: no_speech_prob > threshold AND avg_logprob < threshold → reject
    H4: compression_ratio > threshold → reject

    Args:
        segment: Segment to check
        no_speech_threshold: Threshold for no_speech_prob
        logprob_threshold: Threshold for avg_logprob
        compression_ratio_threshold: Threshold for compression_ratio

    Returns:
        bool: True if segment should be rejected
    """
    # H3: High no-speech probability AND low confidence
    if (segment.no_speech_prob > no_speech_threshold and
            segment.avg_logprob < logprob_threshold):
        return True

    # H4: High compression ratio (repetition/corruption)
    if segment.compression_ratio > compression_ratio_threshold:
        return True

    return False


def should_reject_as_blacklist(
    segment_text: str,
    blacklist_extra: list[str],
) -> bool:
    """
    Check if segment matches built-in or extra blacklist (SPEC §8 H5).

    Full-text match only (after normalization).

    Args:
        segment_text: Segment text to check
        blacklist_extra: User-provided extra blacklist entries

    Returns:
        bool: True if segment matches blacklist
    """
    normalized = normalize_for_match(segment_text)

    # Check built-in blacklist
    for blacklist_entry in BUILTIN_BLACKLIST:
        if normalized == normalize_for_match(blacklist_entry):
            return True

    # Check user extra blacklist
    for extra_entry in blacklist_extra:
        if normalized == normalize_for_match(extra_entry):
            return True

    return False


def should_reject_as_prompt_echo(
    segment_text: str,
    initial_prompt: str,
) -> bool:
    """
    Check if segment is prompt echo (SPEC §8 H6).

    Normalized segment is completely contained in normalized prompt.

    Args:
        segment_text: Segment text
        initial_prompt: Initial prompt used for transcription

    Returns:
        bool: True if segment appears to be prompt echo
    """
    normalized_segment = normalize_for_match(segment_text)
    normalized_prompt = normalize_for_match(initial_prompt)

    # Check for complete containment
    return normalized_segment in normalized_prompt


def filter_segments(
    segments: list[Segment],
    config: dict[str, Any],
    initial_prompt: str,
) -> list[Segment]:
    """
    Filter segments using all hallucination rejection criteria (§8 H3-H6).

    Args:
        segments: List of segments from ASR
        config: Configuration dict with hallucination settings
        initial_prompt: Initial prompt used for transcription

    Returns:
        list[Segment]: Filtered list of segments
    """
    hallucination_cfg = config.get("hallucination", {})
    no_speech_threshold = hallucination_cfg.get("no_speech_threshold", 0.6)
    logprob_threshold = hallucination_cfg.get("logprob_threshold", -1.0)
    compression_ratio_threshold = hallucination_cfg.get("compression_ratio_threshold", 2.4)
    blacklist_extra = hallucination_cfg.get("blacklist_extra", [])

    filtered = []
    for segment in segments:
        # H3/H4: Check probability/compression thresholds
        if should_reject_segment(
            segment,
            no_speech_threshold,
            logprob_threshold,
            compression_ratio_threshold,
        ):
            continue

        # H5: Check blacklist
        if should_reject_as_blacklist(segment.text, blacklist_extra):
            continue

        # H6: Check prompt echo
        if should_reject_as_prompt_echo(segment.text, initial_prompt):
            continue

        filtered.append(segment)

    return filtered
