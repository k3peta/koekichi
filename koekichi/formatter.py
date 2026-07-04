"""Rule-based text formatting (SPEC §9.2 F1-F6)."""

import re
from typing import Any


def format_text(text: str, config: dict[str, Any]) -> str:
    """
    Apply formatting rules F1-F6 in order (SPEC §9.2).

    Pure function: text content (after normalize_for_match) is preserved.

    Args:
        text: Input text
        config: Config dict with format settings

    Returns:
        str: Formatted text
    """
    format_cfg = config.get("format", {})
    language = config.get("language", "ja")
    rules_enabled = format_cfg.get("rules_enabled", True)

    if not rules_enabled:
        return text

    # F1: Strip whitespace from each segment and join (no separator for Japanese)
    text = _apply_f1(text, language)

    # F2: Normalize Japanese punctuation if enabled and lang=ja
    if language == "ja" and format_cfg.get("normalize_ja_punct", True):
        text = _apply_f2(text)

    # F3: Compress consecutive punctuation
    text = _apply_f3(text)

    # F4: Replace 、。 with 。
    text = _apply_f4(text)

    # F5: Remove whitespace around punctuation
    text = _apply_f5(text, language)

    # F6: Ensure final period if enabled
    if format_cfg.get("ensure_final_period", False):
        text = _apply_f6(text, language)

    return text


def _apply_f1(text: str, language: str) -> str:
    """
    F1: Strip leading/trailing whitespace from segments and join.

    For Japanese, no separator. For other languages, preserved as-is.
    """
    # Split by common whitespace to find segments
    # For simplicity, we strip the whole text and preserve internal spacing
    # This is a simplified interpretation: strip leading/trailing spaces only
    text = text.strip()
    return text


def _apply_f2(text: str) -> str:
    """F2: Normalize Japanese punctuation (，→、, ．→。)."""
    text = text.replace("，", "、")
    text = text.replace("．", "。")
    return text


def _apply_f3(text: str) -> str:
    """F3: Compress consecutive identical punctuation."""
    # 。。 → 。
    text = re.sub(r"。+", "。", text)
    # 、、 → 、
    text = re.sub(r"、+", "、", text)
    return text


def _apply_f4(text: str) -> str:
    """F4: Replace 、。(reading mark followed by period) with 。."""
    text = text.replace("、。", "。")
    return text


def _apply_f5(text: str, language: str) -> str:
    """F5: Remove whitespace before/after punctuation."""
    # Remove whitespace before punctuation (。、！？!?)
    text = re.sub(r"\s+([。、！？!?])", r"\1", text)

    if language == "ja":
        # For Japanese, also remove ASCII space after punctuation
        text = re.sub(r"([。、])\s+", r"\1", text)

    return text


def _apply_f6(text: str, language: str) -> str:
    """F6: Ensure final period if text doesn't end with specified punctuation."""
    # Punctuation that can end a sentence
    final_punctuation = {"。", "！", "？", "!", "?", "…", "」", ")"}

    if language == "ja":
        final_punctuation.add("。")

    if text and text[-1] not in final_punctuation:
        text += "。"

    return text
