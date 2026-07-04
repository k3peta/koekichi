"""User dictionary loading and corrections (SPEC §10)."""

import json
import logging
from pathlib import Path
from typing import Any

from koekichi.paths import ensure_config_dir

logger = logging.getLogger(__name__)


def get_dictionary_file() -> Path:
    """Get the path to dictionary.json."""
    return ensure_config_dir() / "dictionary.json"


def load_dictionary() -> dict[str, Any]:
    """
    Load user dictionary from dictionary.json.

    - If file doesn't exist, create empty {"entries": []}.
    - If JSON is corrupted, log error and return empty dict (don't overwrite).
    - Returns dict with "entries" list of word entries.

    Returns:
        dict: Dictionary with "entries" key containing list of entries
    """
    dict_file = get_dictionary_file()

    if not dict_file.exists():
        # Create empty dictionary
        empty_dict = {"entries": []}
        save_dictionary(empty_dict)
        logger.info(f"Created empty dictionary at {dict_file}")
        return empty_dict

    try:
        with open(dict_file, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else {"entries": []}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse dictionary.json: {e}. Using empty dictionary.")
        return {"entries": []}
    except Exception as e:
        logger.error(f"Failed to read dictionary.json: {e}. Using empty dictionary.")
        return {"entries": []}


def save_dictionary(dictionary: dict[str, Any]) -> None:
    """
    Save dictionary to dictionary.json.

    Args:
        dictionary: Dictionary dict to save
    """
    dict_file = get_dictionary_file()
    try:
        with open(dict_file, "w", encoding="utf-8") as f:
            json.dump(dictionary, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved dictionary to {dict_file}")
    except Exception as e:
        logger.error(f"Failed to save dictionary: {e}")


def dictionary_mtime() -> float:
    """
    Return the mtime of dictionary.json, or 0.0 if the file does not exist.

    Returns:
        float: File modification time (0.0 if missing)
    """
    dict_file = get_dictionary_file()
    try:
        return dict_file.stat().st_mtime
    except OSError:
        return 0.0


def load_dictionary_if_changed(
    last_mtime: float,
) -> tuple[dict[str, Any] | None, float]:
    """
    Reload the dictionary if the file mtime changed (SPEC §10.4).

    Args:
        last_mtime: The mtime observed at the previous load

    Returns:
        tuple: (dictionary, new_mtime) if the file changed,
               (None, last_mtime) if unchanged
    """
    current_mtime = dictionary_mtime()
    if current_mtime != last_mtime:
        dictionary = load_dictionary()
        # Re-read mtime after load (load may create the file)
        return dictionary, dictionary_mtime()
    return None, last_mtime


def get_dictionary_words(dictionary: dict[str, Any]) -> list[str]:
    """
    Extract list of word entries from dictionary.

    Args:
        dictionary: Dictionary dict loaded from load_dictionary()

    Returns:
        list[str]: List of "word" fields in order
    """
    entries = dictionary.get("entries", [])
    words = []
    for entry in entries:
        if isinstance(entry, dict) and "word" in entry:
            words.append(entry["word"])
    return words


def apply_corrections(text: str, dictionary: dict[str, Any]) -> str:
    """
    Apply dictionary corrections to text (SPEC §10.3).

    Corrections are applied in descending order of correction string length
    (longest first) to prevent shorter replacements from destroying longer ones.

    Args:
        text: Input text
        dictionary: Dictionary dict from load_dictionary()

    Returns:
        str: Text with corrections applied
    """
    entries = dictionary.get("entries", [])

    # Collect all corrections with their target words
    corrections_list = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        corrections = entry.get("corrections", [])
        word = entry.get("word", "")
        if word and corrections:
            for correction in corrections:
                # Guard: skip empty corrections (text.replace("", word) would
                # insert word between every character)
                if not correction:
                    continue
                corrections_list.append((correction, word))

    # Sort by correction string length (descending)
    corrections_list.sort(key=lambda x: len(x[0]), reverse=True)

    # Apply corrections in order
    for correction, word in corrections_list:
        text = text.replace(correction, word)

    return text
