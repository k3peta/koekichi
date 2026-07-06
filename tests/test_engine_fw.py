"""Test faster-whisper engine backend (SPEC §7.2)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from koekichi.engine.fw import FasterWhisperEngine


class TestFasterWhisperEngineWarmup:
    """Test SPEC §7.2: faster-whisper engine warmup on load()."""

    def test_load_calls_transcribe_for_warmup(self) -> None:
        """load() should call transcribe at least twice: once for warmup."""
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",  # Use tiny for faster test
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

        # Mock WhisperModel to avoid actual model loading
        mock_model = MagicMock()
        # transcribe should return tuples (segments_generator, info)
        # We mock it to return immediately
        mock_model.transcribe.return_value = ([], MagicMock())

        with patch("koekichi.engine.fw.WhisperModel", return_value=mock_model):
            engine = FasterWhisperEngine(config)
            engine.load()

        # Verify transcribe was called for warmup
        assert mock_model.transcribe.called
        # Should be called at least once (for warmup)
        assert mock_model.transcribe.call_count >= 1

        # Check that the warmup call used zeros audio
        first_call_args = mock_model.transcribe.call_args_list[0]
        # args[0] is the audio ndarray
        audio_arg = first_call_args[0][0]
        assert isinstance(audio_arg, np.ndarray)
        assert audio_arg.dtype == np.float32
        assert len(audio_arg) == 8000  # 0.5s @ 16kHz
        assert np.allclose(audio_arg, 0.0)  # All zeros

    def test_warmup_actually_iterates_segments_generator(self) -> None:
        """
        SPEC §7.2 regression test: faster-whisper's transcribe() is lazy —
        the returned segments generator only runs real inference when
        iterated. A warmup that just discards the generator does nothing.
        This test verifies load() actually consumes the generator.
        """
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

        consumed = {"count": 0}

        def _fake_segment_generator():
            # Track that each segment was actually pulled from the generator
            for i in range(3):
                consumed["count"] += 1
                yield MagicMock(
                    text=f"segment{i}",
                    avg_logprob=0.0,
                    no_speech_prob=0.0,
                    compression_ratio=1.0,
                )

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (_fake_segment_generator(), MagicMock())

        with patch("koekichi.engine.fw.WhisperModel", return_value=mock_model):
            engine = FasterWhisperEngine(config)
            engine.load()

        # If load() only discarded the generator (e.g. `_ = self.model.transcribe(...)`
        # without iterating), consumed["count"] would remain 0.
        assert consumed["count"] == 3, (
            "Warmup did not iterate the segments generator; no real inference "
            "was triggered (SPEC §7.2 warmup is a no-op)."
        )

    def test_cpu_warmup_failure_raises(self) -> None:
        """
        SPEC §7.2 (v1.3): warmup failure is no longer swallowed. It also
        serves as the CUDA DLL sanity check, so for an explicit device=cpu
        load a warmup failure must propagate (no fallback target exists).
        """
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("Warmup failed")

        with patch("koekichi.engine.fw.WhisperModel", return_value=mock_model):
            engine = FasterWhisperEngine(config)
            with pytest.raises(RuntimeError):
                engine.load()

        assert engine._model_loaded is False

    def test_cuda_warmup_failure_falls_back_to_cpu(self) -> None:
        """SPEC §7.2 (v1.3): a CUDA load/warmup failure falls back to CPU/int8."""
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "cuda",
                "compute_type": "auto",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

        cuda_model = MagicMock()
        cuda_model.transcribe.side_effect = RuntimeError("cuDNN not found")
        cpu_model = MagicMock()
        cpu_model.transcribe.return_value = (iter([]), MagicMock())

        with patch(
            "koekichi.engine.fw.WhisperModel", side_effect=[cuda_model, cpu_model]
        ) as mock_ctor:
            engine = FasterWhisperEngine(config)
            engine.load()  # should not raise: falls back to cpu

        assert engine._model_loaded is True
        assert engine.resolved_device == "cpu"
        assert engine.resolved_compute_type == "int8"
        assert mock_ctor.call_count == 2

    def test_load_is_idempotent(self) -> None:
        """Multiple load() calls should not re-load or re-transcribe."""
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock())

        with patch("koekichi.engine.fw.WhisperModel", return_value=mock_model):
            engine = FasterWhisperEngine(config)
            engine.load()
            transcribe_count_1 = mock_model.transcribe.call_count

            # Call load again
            engine.load()
            transcribe_count_2 = mock_model.transcribe.call_count

        # Second load should not increase transcribe call count
        assert transcribe_count_1 == transcribe_count_2


class TestDefaultModelResolution:
    """SPEC §7.2 (v1.3): model="auto" resolves by language."""

    def _config(self, language: str) -> dict:
        return {
            "language": language,
            "engine": {
                "backend": "faster-whisper",
                "model": "auto",
                "device": "cpu",
                "compute_type": "int8",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }

    def test_auto_resolves_to_kotoba_for_japanese(self) -> None:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        with patch(
            "koekichi.engine.fw.WhisperModel", return_value=mock_model
        ) as mock_ctor:
            engine = FasterWhisperEngine(self._config("ja"))
            engine.load()
        assert mock_ctor.call_args[0][0] == "kotoba-tech/kotoba-whisper-v2.0-faster"
        assert engine.resolved_model == "kotoba-tech/kotoba-whisper-v2.0-faster"

    def test_auto_resolves_to_small_for_other_languages(self) -> None:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        with patch(
            "koekichi.engine.fw.WhisperModel", return_value=mock_model
        ) as mock_ctor:
            engine = FasterWhisperEngine(self._config("en"))
            engine.load()
        assert mock_ctor.call_args[0][0] == "small"
        assert engine.resolved_model == "small"


class TestDeviceResolution:
    """SPEC §7.2 (v1.3): device="auto" resolves via CUDA availability."""

    def test_auto_resolves_to_cuda_when_available(self) -> None:
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "auto",
                "compute_type": "auto",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        with patch("koekichi.engine.fw._cuda_available", return_value=True), patch(
            "koekichi.engine.fw._register_nvidia_dll_dirs"
        ), patch("koekichi.engine.fw.WhisperModel", return_value=mock_model) as mock_ctor:
            engine = FasterWhisperEngine(config)
            engine.load()
        assert mock_ctor.call_args.kwargs["device"] == "cuda"
        assert mock_ctor.call_args.kwargs["compute_type"] == "float16"
        assert engine.resolved_device == "cuda"

    def test_auto_resolves_to_cpu_when_cuda_unavailable(self) -> None:
        config = {
            "language": "ja",
            "engine": {
                "backend": "faster-whisper",
                "model": "tiny",
                "device": "auto",
                "compute_type": "auto",
                "beam_size": 1,
                "cpu_threads": 0,
            },
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        with patch("koekichi.engine.fw._cuda_available", return_value=False), patch(
            "koekichi.engine.fw.WhisperModel", return_value=mock_model
        ) as mock_ctor:
            engine = FasterWhisperEngine(config)
            engine.load()
        assert mock_ctor.call_args.kwargs["device"] == "cpu"
        assert mock_ctor.call_args.kwargs["compute_type"] == "int8"
        assert engine.resolved_device == "cpu"

    def test_real_cuda_probe_returns_bool(self) -> None:
        """Sanity check: the real probe runs without raising and returns a bool.

        The actual value depends on the machine (True on NVIDIA GPU boxes,
        False elsewhere), so only the contract is asserted here.
        """
        from koekichi.engine.fw import _cuda_available

        assert isinstance(_cuda_available(), bool)


class TestPromptSuppressionForDistil:
    """SPEC §7.2 (v1.3): distilled models must never receive initial_prompt."""

    def _engine_with_resolved_model(self, model_name: str) -> FasterWhisperEngine:
        config = {
            "language": "ja",
            "engine": {"beam_size": 1},
            "hallucination": {
                "no_speech_threshold": 0.6,
                "logprob_threshold": -1.0,
                "compression_ratio_threshold": 2.4,
            },
        }
        engine = FasterWhisperEngine(config)
        engine.model = MagicMock()
        engine.model.transcribe.return_value = ([], MagicMock())
        engine._model_loaded = True
        engine.resolved_model = model_name
        return engine

    def test_kotoba_model_suppresses_nonempty_prompt(self) -> None:
        engine = self._engine_with_resolved_model(
            "kotoba-tech/kotoba-whisper-v2.0-faster"
        )
        engine.transcribe(np.zeros(1600, dtype=np.float32), "こんにちは、辞書。", "ja")
        assert engine.model.transcribe.call_args.kwargs["initial_prompt"] is None

    def test_distil_model_suppresses_empty_prompt_too(self) -> None:
        engine = self._engine_with_resolved_model("distil-whisper/distil-large-v3")
        engine.transcribe(np.zeros(1600, dtype=np.float32), "", "ja")
        assert engine.model.transcribe.call_args.kwargs["initial_prompt"] is None

    def test_non_distil_model_keeps_prompt(self) -> None:
        engine = self._engine_with_resolved_model("small")
        engine.transcribe(np.zeros(1600, dtype=np.float32), "こんにちは、辞書。", "ja")
        assert (
            engine.model.transcribe.call_args.kwargs["initial_prompt"]
            == "こんにちは、辞書。"
        )

    def test_is_distil_model_matches_kotoba_and_distil(self) -> None:
        from koekichi.engine.fw import _is_distil_model

        assert _is_distil_model("kotoba-tech/kotoba-whisper-v2.0-faster") is True
        assert _is_distil_model("distil-whisper/distil-large-v3") is True
        assert _is_distil_model("small") is False
        assert _is_distil_model("large-v3") is False
