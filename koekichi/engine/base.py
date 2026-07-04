"""Abstract ASR engine interface (SPEC §7.1)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class Segment:
    """
    ASR output segment (SPEC §7.1).

    Attributes:
        text: Recognized text
        avg_logprob: Average log probability (0.0 if unavailable)
        no_speech_prob: Probability of no speech (0.0 if unavailable)
        compression_ratio: Text compression ratio (0.0 if unavailable)
    """
    text: str
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    compression_ratio: float = 0.0


class EngineBase(ABC):
    """Abstract base class for ASR engines."""

    @abstractmethod
    def load(self) -> None:
        """
        Load the model (idempotent).

        Should be safe to call multiple times without reloading.
        """
        pass

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray,
        initial_prompt: str,
        language: str,
    ) -> list[Segment]:
        """
        Transcribe audio using the model.

        Args:
            audio: Audio data (float32 ndarray, 16kHz mono)
            initial_prompt: Initial prompt to guide Whisper (§9.1)
            language: Language code (e.g., "ja")

        Returns:
            list[Segment]: List of transcribed segments
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the name of this engine.

        Returns:
            str: Engine name (e.g., "mlx-whisper", "faster-whisper")
        """
        pass
