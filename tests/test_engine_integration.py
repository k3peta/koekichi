"""Integration tests for ASR engines (SPEC §17, Mac only, @pytest.mark.integration).

These tests run real transcription with the mlx backend. The first run may
trigger a model download from HuggingFace Hub (mlx-community/whisper-large-v3-turbo,
~1.6GB), which can take several minutes.
"""

import platform
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from koekichi.antihallucination import (
    BUILTIN_BLACKLIST,
    filter_segments,
    normalize_for_match,
)
from koekichi.engine import get_engine
from koekichi.prompt import build_prompt


def _is_mac_arm64() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _kyoko_available() -> bool:
    """Check whether the Kyoko voice is available for `say`."""
    if shutil.which("say") is None:
        return False
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return "Kyoko" in result.stdout
    except Exception:
        return False


def _synthesize_ja_wav(text: str, out_dir: Path) -> np.ndarray:
    """
    Generate Japanese speech with `say -v Kyoko`, convert to 16kHz mono WAV
    via afconvert, and return it as a normalized float32 ndarray.
    """
    aiff_path = out_dir / "speech.aiff"
    wav_path = out_dir / "speech.wav"

    subprocess.run(
        ["say", "-v", "Kyoko", "-o", str(aiff_path), text],
        check=True,
        timeout=60,
    )
    subprocess.run(
        [
            "afconvert",
            "-f", "WAVE",
            "-d", "LEI16@16000",
            "-c", "1",
            str(aiff_path),
            str(wav_path),
        ],
        check=True,
        timeout=60,
    )

    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        raw = wf.readframes(wf.getnframes())

    audio_int16 = np.frombuffer(raw, dtype=np.int16)
    return audio_int16.astype(np.float32) / 32768.0


DEFAULT_CONFIG = {
    "language": "ja",
    "engine": {
        "backend": "auto",
        "model": "auto",
        "beam_size": 1,
    },
    "hallucination": {
        "no_speech_threshold": 0.6,
        "logprob_threshold": -1.0,
        "compression_ratio_threshold": 2.4,
        "blacklist_extra": [],
    },
}


@pytest.mark.integration
class TestEngineIntegration:
    """Real transcription tests (SPEC §17 integration plan)."""

    @pytest.fixture(autouse=True)
    def skip_if_not_mac_arm64(self) -> None:
        """Skip all tests in this class if not on Mac with Apple Silicon."""
        if not _is_mac_arm64():
            pytest.skip("Integration tests only run on macOS with Apple Silicon")

    def test_transcribe_japanese_speech(self, tmp_path: Path) -> None:
        """
        Synthesize Japanese speech with Kyoko, transcribe with the auto (mlx)
        backend, and verify expected words appear and no blacklist sentence
        is present.

        Note: the first run downloads the mlx whisper model (~1.6GB).
        """
        if not _kyoko_available():
            pytest.skip("Kyoko voice not available for `say`")

        text = "明日の会議は午後三時から始まります"
        audio = _synthesize_ja_wav(text, tmp_path)

        config = DEFAULT_CONFIG
        engine = get_engine(config)
        assert engine.name == "mlx-whisper"
        engine.load()

        initial_prompt = build_prompt([])
        segments = engine.transcribe(audio, initial_prompt, "ja")
        filtered = filter_segments(segments, config, initial_prompt)
        joined = "".join(seg.text for seg in filtered)

        assert "会議" in joined, f"Expected 会議 in transcription: {joined!r}"
        assert ("三時" in joined) or ("3時" in joined), (
            f"Expected 三時/3時 in transcription: {joined!r}"
        )

        normalized = normalize_for_match(joined)
        for blacklisted in BUILTIN_BLACKLIST:
            assert normalize_for_match(blacklisted) not in normalized, (
                f"Blacklist sentence leaked into output: {blacklisted!r}"
            )

    def test_transcribe_silence_is_empty(self) -> None:
        """
        Transcribing 2 seconds of silence and applying the hallucination
        filter must produce empty text.

        Note: the first run downloads the mlx whisper model (~1.6GB).
        """
        config = DEFAULT_CONFIG
        engine = get_engine(config)
        engine.load()

        silence = np.zeros(16000 * 2, dtype=np.float32)
        initial_prompt = build_prompt([])
        segments = engine.transcribe(silence, initial_prompt, "ja")
        filtered = filter_segments(segments, config, initial_prompt)
        joined = "".join(seg.text for seg in filtered).strip()

        assert joined == "", f"Expected empty output for silence, got {joined!r}"
