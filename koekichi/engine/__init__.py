"""ASR engine factory and selection (SPEC §7)."""

import logging
import platform
import sys
from typing import Any

from koekichi.engine.base import EngineBase

logger = logging.getLogger(__name__)


def get_engine(config: dict[str, Any]) -> EngineBase:
    """
    Factory function to get appropriate ASR engine based on config and platform.

    SPEC §7: backend = "auto" → darwin/arm64 uses mlx-whisper, others use faster-whisper.

    Args:
        config: Configuration dict with engine.backend setting

    Returns:
        EngineBase: Instantiated engine

    Raises:
        ValueError: If backend is not supported on this platform
    """
    engine_cfg = config.get("engine", {})
    backend = engine_cfg.get("backend", "auto").lower()

    # Determine platform
    is_darwin = sys.platform == "darwin"
    is_arm64 = platform.machine() == "arm64"

    # Resolve "auto" backend
    if backend == "auto":
        if is_darwin and is_arm64:
            backend = "mlx"
        else:
            backend = "faster-whisper"

    logger.info(f"Using ASR backend: {backend}")

    # Import and instantiate engine
    if backend == "mlx":
        if not (is_darwin and is_arm64):
            raise ValueError(
                "mlx-whisper only supported on macOS with Apple Silicon (arm64)"
            )
        try:
            from koekichi.engine.mlx import MLXWhisperEngine
            return MLXWhisperEngine(config)
        except ImportError as e:
            logger.error(f"Failed to import mlx-whisper: {e}")
            raise ValueError(f"mlx-whisper unavailable: {e}")

    elif backend == "faster-whisper":
        try:
            from koekichi.engine.fw import FasterWhisperEngine
            return FasterWhisperEngine(config)
        except ImportError as e:
            logger.error(f"Failed to import faster-whisper: {e}")
            raise ValueError(f"faster-whisper unavailable: {e}")

    else:
        raise ValueError(f"Unknown ASR backend: {backend}")
