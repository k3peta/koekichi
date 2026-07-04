"""Faster-Whisper ASR engine backend (SPEC §7.2)."""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
from faster_whisper import WhisperModel

from koekichi.engine.base import EngineBase, Segment

logger = logging.getLogger(__name__)


class FasterWhisperEngine(EngineBase):
    """ASR engine using faster-whisper (CTranslate2 backend)."""

    def __init__(self, config: dict[str, Any]):
        """
        Initialize faster-whisper engine.

        Args:
            config: Configuration dict with engine settings
        """
        self.config = config
        self.model = None
        self._model_loaded = False
        self.resolved_model = ""
        self.resolved_device = ""
        self.resolved_compute_type = ""

    def load(self) -> None:
        """Load the Whisper model (idempotent)."""
        if self._model_loaded and self.model is not None:
            return

        engine_cfg = self.config.get("engine", {})
        model = engine_cfg.get("model", "auto")
        device = engine_cfg.get("device", "auto")
        compute_type = engine_cfg.get("compute_type", "int8")
        cpu_threads = engine_cfg.get("cpu_threads", 0)

        # Default model for faster-whisper: for Japanese use the
        # JA-specialized distilled large-v3 (kotoba-whisper), which gives
        # large-v3-class Japanese accuracy at medium-class compute --
        # far fewer mistranscriptions than "small" on CPU-only machines.
        # Other languages keep the multilingual "small".
        if model == "auto":
            if str(self.config.get("language", "ja")).lower() == "ja":
                model = "kotoba-tech/kotoba-whisper-v2.0-faster"
            else:
                model = "small"

        # Device auto-detection: use CUDA when CTranslate2 can see a GPU.
        # Actually running on it also needs the cuDNN/cuBLAS DLLs, which we
        # verify via the warmup below -- on any failure we fall back to CPU.
        if device in ("auto", "cuda"):
            _register_nvidia_dll_dirs()
        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"

        # "int8" (the long-standing default written into existing
        # config.json files) and "auto" are CPU-oriented; on CUDA use
        # float16 for better speed and accuracy. Any other explicit value
        # (e.g. int8_float16) is respected as-is.
        resolved_compute = compute_type
        if device == "cuda" and compute_type in ("auto", "int8"):
            resolved_compute = "float16"
        elif compute_type == "auto":
            resolved_compute = "int8"

        try:
            self._load_with(model, device, resolved_compute, cpu_threads)
        except Exception as e:
            if device != "cuda":
                logger.error(f"Failed to load faster-whisper model: {e}")
                self._model_loaded = False
                raise
            logger.warning(
                f"CUDA load/warmup failed ({e}); falling back to cpu/int8. "
                "GPU use requires the CUDA 12 + cuDNN 9 DLLs on PATH (see BUILD.md)."
            )
            try:
                self._load_with(model, "cpu", "int8", cpu_threads)
            except Exception as e2:
                logger.error(f"Failed to load faster-whisper model on CPU: {e2}")
                self._model_loaded = False
                raise

    def _load_with(
        self, model: str, device: str, compute_type: str, cpu_threads: int
    ) -> None:
        """Load WhisperModel with explicit device/compute_type and warm it up.

        Raises on failure (caller decides whether to fall back to CPU).
        """
        logger.info(
            f"Loading faster-whisper model: {model} "
            f"(device={device}, compute_type={compute_type})"
        )
        self.model = WhisperModel(
            model,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads if cpu_threads > 0 else 0,
        )
        # Warm up: CTranslate2 defers thread-pool/kernel setup to the
        # first transcribe() call. Run a short silent transcription now
        # so that cost lands during preload, not the first real
        # recording (SPEC §15 preload requirement; mirrors mlx.py).
        # On CUDA this also proves the cuDNN/cuBLAS DLLs actually work.
        # NOTE: transcribe() is lazy (returns a generator); must iterate
        # it to actually force the inference to run.
        warmup_audio = np.zeros(8000, dtype=np.float32)  # 0.5s @ 16kHz
        warmup_segments, _ = self.model.transcribe(warmup_audio, language="ja", beam_size=1)
        for _seg in warmup_segments:
            pass
        self.resolved_model = model
        self.resolved_device = device
        self.resolved_compute_type = compute_type
        self._model_loaded = True
        logger.info(
            f"Faster-whisper model loaded and warmed up ({device}/{compute_type})"
        )

    def transcribe(
        self,
        audio: np.ndarray,
        initial_prompt: str,
        language: str,
    ) -> list[Segment]:
        """
        Transcribe audio using faster-whisper.

        Args:
            audio: Audio data (float32 ndarray, 16kHz mono)
            initial_prompt: Initial prompt for Whisper
            language: Language code (e.g., "ja")

        Returns:
            list[Segment]: List of transcribed segments
        """
        if not self._model_loaded or self.model is None:
            self.load()

        engine_cfg = self.config.get("engine", {})
        beam_size = engine_cfg.get("beam_size", 1)

        hallucination_cfg = self.config.get("hallucination", {})
        no_speech_threshold = hallucination_cfg.get("no_speech_threshold", 0.6)
        logprob_threshold = hallucination_cfg.get("logprob_threshold", -1.0)
        compression_ratio_threshold = hallucination_cfg.get("compression_ratio_threshold", 2.4)

        # Distilled models (kotoba-whisper / distil-whisper) were not trained
        # with prompt conditioning: any initial_prompt -- even an empty
        # string -- makes them mistranscribe and truncate output (verified
        # 2026-07-06: "辞書"→"事書", second sentence dropped). Suppress the
        # prompt for them; dictionary corrections still apply post-ASR.
        prompt: str | None = initial_prompt or None
        if prompt and _is_distil_model(self.resolved_model):
            prompt = None

        try:
            segments, info = self.model.transcribe(
                audio,
                language=language,
                beam_size=beam_size,
                condition_on_previous_text=False,
                vad_filter=True,
                no_speech_threshold=no_speech_threshold,
                log_prob_threshold=logprob_threshold,
                compression_ratio_threshold=compression_ratio_threshold,
                initial_prompt=prompt,
            )

            # Convert to Segment objects
            result = []
            for seg in segments:
                result.append(
                    Segment(
                        text=seg.text,
                        avg_logprob=seg.avg_logprob if hasattr(seg, "avg_logprob") else 0.0,
                        no_speech_prob=seg.no_speech_prob if hasattr(seg, "no_speech_prob") else 0.0,
                        compression_ratio=seg.compression_ratio if hasattr(seg, "compression_ratio") else 0.0,
                    )
                )
            return result

        except Exception as e:
            logger.error(f"Transcription error in faster-whisper: {e}")
            raise

    @property
    def name(self) -> str:
        """Return engine name (with device once the model is loaded)."""
        if self.resolved_device:
            return f"faster-whisper/{self.resolved_device}"
        return "faster-whisper"


def _nvidia_dll_candidate_dirs() -> list[Path]:
    """Directories that may hold the CUDA runtime DLLs, best first.

    1. `%LOCALAPPDATA%\\KoeKichi\\cuda\\bin` -- populated by the installer's
       optional GPU task / the "KoeKichi GPU セットアップ" shortcut
       (packaging/install_gpu_dlls.ps1). Works for the frozen exe.
    2. The `nvidia-*-cu12` pip wheels' bin dirs (the `gpu` extra) --
       source runs via `uv sync --extra gpu`.
    """
    dirs: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "KoeKichi" / "cuda" / "bin")

    import importlib

    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            mod = importlib.import_module(pkg)
            dirs.append(Path(list(mod.__path__)[0]) / "bin")
        except Exception:
            pass
    return dirs


def _register_nvidia_dll_dirs() -> None:
    """Make cuBLAS/cuDNN loadable without a system CUDA Toolkit install.

    CTranslate2 resolves cublas64_12.dll / cudnn*.dll via the standard
    Windows DLL search, so adding the candidate dirs to the search path is
    enough. No-op for dirs that don't exist. No-op entirely off Windows.
    """
    if sys.platform != "win32":
        return
    for bin_dir in _nvidia_dll_candidate_dirs():
        try:
            if bin_dir.is_dir():
                os.add_dll_directory(str(bin_dir))
                os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
                logger.debug(f"Registered NVIDIA DLL dir: {bin_dir}")
        except Exception:
            pass


def _cuda_available() -> bool:
    """Return True if CTranslate2 reports at least one CUDA device."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def _is_distil_model(model_name: str) -> bool:
    """Return True for distilled Whisper variants that mishandle prompts."""
    lowered = model_name.lower()
    return "kotoba" in lowered or "distil" in lowered
