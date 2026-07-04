"""MLX-Whisper ASR engine backend (SPEC §7.3, darwin/arm64 only)."""

import logging
from typing import Any

import numpy as np

from koekichi.engine.base import EngineBase, Segment

logger = logging.getLogger(__name__)

# Note: This module should only be imported on darwin/arm64
# The factory in engine/__init__.py handles conditional import


def _get_mlx_whisper():
    """Lazy import mlx_whisper (to avoid ImportError on non-arm64 systems)."""
    try:
        import mlx_whisper
        return mlx_whisper
    except ImportError as e:
        logger.error(f"mlx_whisper not available: {e}")
        raise


class MLXWhisperEngine(EngineBase):
    """ASR engine using mlx-whisper (Apple Silicon GPU)."""

    def __init__(self, config: dict[str, Any]):
        """
        Initialize mlx-whisper engine.

        Args:
            config: Configuration dict with engine settings
        """
        self.config = config
        self.mlx_whisper = None
        self._model_loaded = False
        self._model_name = None

    def load(self) -> None:
        """Load the Whisper model (idempotent)."""
        if self._model_loaded:
            return

        mlx_whisper = _get_mlx_whisper()

        engine_cfg = self.config.get("engine", {})
        model = engine_cfg.get("model", "auto")

        # Default model for mlx-whisper
        if model == "auto":
            model = "mlx-community/whisper-large-v3-turbo"

        try:
            logger.info(f"Loading mlx-whisper model: {model}")
            self.mlx_whisper = mlx_whisper
            self._model_name = model
            # Warm up: mlx_whisper loads the model lazily on first transcribe.
            # Run a short silent transcription so the model is resident before
            # the first real request (SPEC §15 preload requirement).
            warmup_audio = np.zeros(8000, dtype=np.float32)  # 0.5s @ 16kHz
            mlx_whisper.transcribe(
                warmup_audio,
                path_or_hf_repo=model,
                word_timestamps=False,
            )
            self._model_loaded = True
            logger.info("MLX-Whisper model loaded and warmed up")
        except Exception as e:
            logger.error(f"Failed to initialize mlx-whisper: {e}")
            self._model_loaded = False
            raise

    def transcribe(
        self,
        audio: np.ndarray,
        initial_prompt: str,
        language: str,
    ) -> list[Segment]:
        """
        Transcribe audio using mlx-whisper.

        Args:
            audio: Audio data (float32 ndarray, 16kHz mono)
            initial_prompt: Initial prompt for Whisper
            language: Language code (e.g., "ja")

        Returns:
            list: List of Segment-like objects
        """
        if not self._model_loaded:
            self.load()

        mlx_whisper = _get_mlx_whisper()

        engine_cfg = self.config.get("engine", {})

        hallucination_cfg = self.config.get("hallucination", {})
        no_speech_threshold = hallucination_cfg.get("no_speech_threshold", 0.6)
        logprob_threshold = hallucination_cfg.get("logprob_threshold", -1.0)
        compression_ratio_threshold = hallucination_cfg.get("compression_ratio_threshold", 2.4)

        try:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self._model_name,
                language=language,
                initial_prompt=initial_prompt,
                condition_on_previous_text=False,
                no_speech_threshold=no_speech_threshold,
                logprob_threshold=logprob_threshold,
                compression_ratio_threshold=compression_ratio_threshold,
                word_timestamps=False,
            )

            # Convert to Segment objects
            segments = []
            for seg in result.get("segments", []):
                segments.append(
                    Segment(
                        text=seg.get("text", ""),
                        avg_logprob=seg.get("avg_logprob", 0.0),
                        no_speech_prob=seg.get("no_speech_prob", 0.0),
                        compression_ratio=seg.get("compression_ratio", 0.0),
                    )
                )
            return segments

        except Exception as e:
            logger.error(f"Transcription error in mlx-whisper: {e}")
            raise

    @property
    def name(self) -> str:
        """Return engine name."""
        return "mlx-whisper"
