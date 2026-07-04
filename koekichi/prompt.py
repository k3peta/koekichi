"""Initial prompt construction for Whisper (SPEC §9.1)."""

# SPEC §9.1: Fixed seed prompt to guide Whisper towards punctuation
SEED = "こんにちは、今日は音声入力のテストです。よろしくお願いします。"
MAX_PROMPT_LENGTH = 200


def build_prompt(dictionary_words: list[str]) -> str:
    """
    Build initial_prompt from SEED and dictionary words.

    Concatenates SEED with dictionary words (joined by '、' with trailing '。').
    If total length exceeds MAX_PROMPT_LENGTH, truncates dictionary words
    but always includes SEED.

    Args:
        dictionary_words: List of dictionary word entries (empty ok)

    Returns:
        str: Constructed prompt (≤ 200 chars)
    """
    if not dictionary_words:
        return SEED

    # Join dictionary words with '、' and add trailing '。'
    dict_part = "、".join(dictionary_words) + "。"

    # Combine: SEED + dict_part
    combined = SEED + dict_part

    # If within limit, return
    if len(combined) <= MAX_PROMPT_LENGTH:
        return combined

    # Truncate dictionary part to fit
    # Calculate available space: MAX - SEED length
    available = MAX_PROMPT_LENGTH - len(SEED)

    # Greedily fit dictionary words (with separators) into available space
    if available <= 0:
        return SEED

    # Rebuild with as many dictionary words as fit
    dict_words_fitted = []
    current_length = 0

    for i, word in enumerate(dictionary_words):
        # Length contribution: word + separator (either '、' or '。')
        word_length = len(word) + 1  # +1 for '、' or '。'

        if current_length + word_length <= available:
            dict_words_fitted.append(word)
            current_length += word_length
        else:
            break

    if not dict_words_fitted:
        return SEED

    # Join fitted words
    fitted_part = "、".join(dict_words_fitted) + "。"
    return SEED + fitted_part
