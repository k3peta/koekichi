"""LLM-based formatting with content-preservation guard (SPEC §9.3)."""

import logging
from typing import Any

from koekichi.antihallucination import normalize_for_match

logger = logging.getLogger(__name__)

# Fixed system prompt (SPEC §9.3)
SYSTEM_PROMPT = """あなたは文字起こしテキストの校正器です。与えられたテキストの句読点(、。)と明らかな表記の乱れのみを修正してください。単語の追加・削除・言い換え・要約は禁止です。修正後の本文のみを出力し、説明や前置きを付けないでください。"""


def format_with_llm(text: str, config: dict[str, Any]) -> str:
    """
    Format text using LLM (Ollama) if enabled, with content-preservation guard.

    If LLM is disabled, returns text unchanged.
    If LLM fails, returns text unchanged.
    If LLM output changes content (by normalize_for_match), logs and returns
    original rule-formatted text.

    Args:
        text: Text to format
        config: Configuration dict

    Returns:
        str: Formatted text (or original if LLM fails/disabled)
    """
    llm_cfg = config.get("format", {}).get("llm", {})

    if not llm_cfg.get("enabled", False):
        return text

    endpoint = llm_cfg.get("endpoint", "http://127.0.0.1:11434")
    model = llm_cfg.get("model", "qwen2.5:3b-instruct")
    timeout_s = llm_cfg.get("timeout_s", 6)

    try:
        import requests
    except ImportError:
        logger.warning("requests not available for LLM formatting, skipping")
        return text

    # Normalize input for comparison
    input_normalized = normalize_for_match(text)

    try:
        response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "stream": False,
            },
            timeout=timeout_s,
        )
        response.raise_for_status()

        result = response.json()
        llm_output = result.get("message", {}).get("content", "").strip()

        if not llm_output:
            logger.warning("LLM returned empty response, using original")
            return text

        # Content-preservation guard: check if output changes the content
        output_normalized = normalize_for_match(llm_output)

        if input_normalized != output_normalized:
            logger.info(
                "LLM output differs from input (by content), using rule-formatted text"
            )
            return text

        return llm_output

    except requests.exceptions.Timeout:
        logger.warning("LLM request timed out, using rule-formatted text")
        return text
    except requests.exceptions.ConnectionError:
        logger.warning("LLM connection failed, using rule-formatted text")
        return text
    except requests.exceptions.HTTPError as e:
        logger.warning(f"LLM HTTP error: {e}, using rule-formatted text")
        return text
    except Exception as e:
        logger.warning(f"LLM formatting failed: {e}, using rule-formatted text")
        return text
