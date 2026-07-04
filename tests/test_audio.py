"""Tests for audio recording with resident stream (SPEC §6.0, §17).

No real audio device is used: sd.InputStream is mocked and the callback
_on_audio() is invoked directly with fake data.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from koekichi.audio import AudioRecorder


def _make_recorder(**kwargs) -> AudioRecorder:
    defaults = dict(
        device=None,
        sample_rate=16000,
        max_duration_s=120,
        idle_stream="running",
        pre_roll_ms=200,
    )
    defaults.update(kwargs)
    return AudioRecorder(**defaults)


def _make_fake_stream() -> MagicMock:
    """A fake InputStream whose .active tracks start()/stop() calls."""
    stream = MagicMock()
    stream.active = False

    def _start():
        stream.active = True

    def _stop():
        stream.active = False

    stream.start.side_effect = _start
    stream.stop.side_effect = _stop
    return stream


@pytest.fixture
def fake_input_stream():
    """Patch sd.InputStream so no real device is opened."""
    streams: list[MagicMock] = []

    def _factory(*args, **kwargs):
        stream = _make_fake_stream()
        streams.append(stream)
        return stream

    with patch("koekichi.audio.sd.InputStream", side_effect=_factory) as mock_cls:
        mock_cls.created_streams = streams
        yield mock_cls


def _feed(recorder: AudioRecorder, chunk: np.ndarray, times: int = 1) -> None:
    """Feed fake audio into the callback directly."""
    for _ in range(times):
        recorder._on_audio(chunk.reshape(-1, 1), len(chunk), None, None)


class TestPrerollBuffer:
    """Test preroll ringbuffer functionality."""

    def test_preroll_accumulation(self) -> None:
        """Preroll accumulates audio without capturing."""
        recorder = _make_recorder()
        chunk = np.random.randn(512).astype(np.float32)

        # ~320ms of audio (10 x 512 samples @16kHz), exceeds 200ms preroll
        _feed(recorder, chunk, times=10)

        max_samples = (recorder.pre_roll_ms * recorder.sample_rate) // 1000
        assert recorder.pre_roll_total_samples <= max_samples
        # No capture happened
        assert recorder.capture_chunks == []

    def test_preroll_cap_with_large_input(self) -> None:
        """Even with lots of input, the deque never exceeds the sample cap."""
        recorder = _make_recorder()
        chunk = np.random.randn(512).astype(np.float32)

        _feed(recorder, chunk, times=1000)

        assert recorder.pre_roll_total_samples <= recorder.pre_roll_max_samples
        assert (
            sum(len(c) for c in recorder.pre_roll_buffer)
            == recorder.pre_roll_total_samples
        )

    def test_preroll_disabled(self) -> None:
        """With pre_roll_ms=0, no preroll buffer is used."""
        recorder = _make_recorder(pre_roll_ms=0)
        chunk = np.random.randn(512).astype(np.float32)

        _feed(recorder, chunk)

        assert recorder.pre_roll_max_samples == 0
        assert len(recorder.pre_roll_buffer) == 0


class TestCapturingGate:
    """Test capturing flag gates recording."""

    def test_capture_after_preroll(self, fake_input_stream) -> None:
        """start_recording copies preroll; stop_recording returns concatenated audio."""
        recorder = _make_recorder()
        recorder.open_stream()

        chunk = np.random.randn(512).astype(np.float32)
        _feed(recorder, chunk, times=5)
        preroll_count = len(recorder.pre_roll_buffer)

        recorder.start_recording()
        assert recorder._capturing is True
        assert len(recorder.capture_chunks) == preroll_count

        _feed(recorder, chunk, times=3)
        assert len(recorder.capture_chunks) == preroll_count + 3

        result = recorder.stop_recording()
        assert result.shape[0] == (preroll_count + 3) * 512
        assert recorder._capturing is False

    def test_data_before_capture_not_included(self, fake_input_stream) -> None:
        """Only the last pre_roll_ms of pre-capture data is at the head of the result."""
        recorder = _make_recorder()
        recorder.open_stream()

        old_chunk = np.full(512, 0.9, dtype=np.float32)
        recent_chunk = np.full(512, 0.1, dtype=np.float32)

        # Old data far beyond the preroll cap, then recent data filling it
        _feed(recorder, old_chunk, times=20)
        _feed(recorder, recent_chunk, times=6)  # 6*512=3072 < 3200 sample cap

        recorder.start_recording()
        result = recorder.stop_recording()

        # Result must fit within preroll cap and contain no old data
        assert result.shape[0] <= recorder.pre_roll_max_samples
        assert not np.any(result > 0.5)

    def test_no_preroll_copy_in_stopped_mode(self, fake_input_stream) -> None:
        """When idle_stream='stopped', preroll is not copied on start."""
        recorder = _make_recorder(idle_stream="stopped")
        recorder.open_stream()

        chunk = np.random.randn(512).astype(np.float32)
        _feed(recorder, chunk, times=5)

        recorder.start_recording()
        assert recorder._capturing is True
        assert len(recorder.capture_chunks) == 0


class TestMaxDuration:
    """Test max_duration_s enforcement."""

    def test_max_duration_reached(self, fake_input_stream) -> None:
        """reached_max_duration flag is set when capture exceeds max_duration_s."""
        recorder = _make_recorder(max_duration_s=2)
        recorder.open_stream()
        recorder.start_recording()

        chunk = np.random.randn(512).astype(np.float32)
        num_chunks = int((2 * 1.1 * 16000) / 512)
        for _ in range(num_chunks):
            _feed(recorder, chunk)
            if recorder.reached_max_duration:
                break

        assert recorder.reached_max_duration is True


class TestStreamLifecycle:
    """Test stream create/start/stop/close behavior (mocked device)."""

    def test_stopped_mode_no_stream_recreation(self, fake_input_stream) -> None:
        """stopped mode: open_stream + 2 recordings create only ONE InputStream."""
        recorder = _make_recorder(idle_stream="stopped")

        recorder.open_stream()
        stream = recorder.stream
        # open_stream warms up: start then stop -> idle stream is inactive
        assert stream.start.call_count == 1
        assert stream.stop.call_count == 1
        assert stream.active is False

        # First recording
        recorder.start_recording()
        assert stream.start.call_count == 2
        assert stream.active is True
        recorder.stop_recording()
        assert stream.stop.call_count == 2
        assert stream.active is False

        # Second recording
        recorder.start_recording()
        assert stream.start.call_count == 3
        recorder.stop_recording()
        assert stream.stop.call_count == 3

        # Only one InputStream ever created (no recreation per recording)
        assert fake_input_stream.call_count == 1
        assert recorder.stream is stream

    def test_running_mode_restarts_inactive_stream(self, fake_input_stream) -> None:
        """running mode: a dead (inactive) stream is start()ed again on start_recording."""
        recorder = _make_recorder(idle_stream="running")
        recorder.open_stream()
        stream = recorder.stream
        assert stream.active is True

        # Simulate the stream dying while idle
        stream.active = False

        recorder.start_recording()
        # start() was retried on the same stream (no recreation needed)
        assert stream.active is True
        assert fake_input_stream.call_count == 1
        assert recorder._capturing is True

    def test_running_mode_recreates_on_restart_failure(self, fake_input_stream) -> None:
        """running mode: if restart fails, the old stream is closed and recreated."""
        recorder = _make_recorder(idle_stream="running")
        recorder.open_stream()
        old_stream = recorder.stream

        # Make the old stream dead and un-startable
        old_stream.active = False
        old_stream.start.side_effect = RuntimeError("device gone")

        recorder.start_recording()

        assert recorder.stream is not old_stream
        old_stream.close.assert_called_once()
        assert fake_input_stream.call_count == 2
        assert recorder._capturing is True

    def test_open_stream_idempotent(self, fake_input_stream) -> None:
        """open_stream twice creates only one stream."""
        recorder = _make_recorder()
        recorder.open_stream()
        recorder.open_stream()
        assert fake_input_stream.call_count == 1

    def test_close_clears_state(self, fake_input_stream) -> None:
        """close() leaves stream None and _capturing False."""
        recorder = _make_recorder()
        recorder.open_stream()
        stream = recorder.stream
        recorder.start_recording()

        recorder.close()

        stream.stop.assert_called()
        stream.close.assert_called_once()
        assert recorder.stream is None
        assert recorder._capturing is False
        assert recorder.capture_chunks == []


class TestRMS:
    """Test RMS level calculation."""

    def test_rms_from_preroll(self) -> None:
        """get_current_rms reads from preroll when not capturing."""
        recorder = _make_recorder()
        silent_chunk = np.zeros(512, dtype=np.float32)
        _feed(recorder, silent_chunk)

        assert recorder.get_current_rms() == pytest.approx(0.0, abs=1e-6)

    def test_rms_from_capture(self, fake_input_stream) -> None:
        """get_current_rms reads from capture chunks when capturing."""
        recorder = _make_recorder()
        recorder.open_stream()
        recorder.start_recording()

        loud_chunk = np.full(512, 0.5, dtype=np.float32)
        _feed(recorder, loud_chunk)

        assert recorder.get_current_rms() > 0.4


class TestEmptyRecording:
    """Test edge cases with empty or minimal audio."""

    def test_empty_stop_recording(self) -> None:
        """stop_recording on idle recorder returns empty array."""
        recorder = _make_recorder()
        result = recorder.stop_recording()
        assert result.shape[0] == 0
        assert result.dtype == np.float32

    def test_start_stop_no_audio(self, fake_input_stream) -> None:
        """start then immediately stop (no audio, no preroll) returns empty array."""
        recorder = _make_recorder(pre_roll_ms=0)
        recorder.open_stream()
        recorder.start_recording()
        result = recorder.stop_recording()
        assert result.shape[0] == 0
