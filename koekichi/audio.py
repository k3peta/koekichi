"""Audio recording via sounddevice (SPEC §6).

Resident stream mode: InputStream is opened at startup and kept running,
with a preroll ringbuffer to capture ~200ms of audio before "capture" begins.
This reduces start latency from 100-130ms to <5ms (SPEC §6.0, §15).
"""

import collections
import logging
from threading import Lock
from typing import Any

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

# Track logged status messages to avoid spam (same status logged once)
_LAST_STATUS_LOGGED: dict[str, str] = {}


class AudioRecorder:
    """
    Audio recorder using sounddevice (16kHz mono float32).

    SPEC §6.0: Uses a resident stream (open_stream) to achieve <5ms start
    latency. Preroll ringbuffer holds recent audio; capturing flag gates
    recording into the capture list.

    Locking (deadlock avoidance):
    - ``_buffer_lock``: buffers/flags only. The audio callback takes ONLY this.
    - ``_device_lock``: stream create/start/stop/close only.
    NEVER hold _buffer_lock across a device call — PortAudio's stop() waits
    for the running callback to finish, and the callback blocks on
    _buffer_lock, so holding both deadlocks. If both are needed, the only
    allowed order is _device_lock -> _buffer_lock.
    """

    def __init__(
        self,
        device: int | None = None,
        sample_rate: int = 16000,
        max_duration_s: float = 120,
        idle_stream: str = "running",
        pre_roll_ms: int = 200,
    ):
        """
        Initialize audio recorder.

        Args:
            device: Device index (None = default input)
            sample_rate: Sample rate (default 16000)
            max_duration_s: Maximum recording duration (default 120s)
            idle_stream: "running" (always on, <5ms start) or "stopped" (~140ms start)
            pre_roll_ms: Preroll ringbuffer size in ms (0 to disable)
        """
        self.device = device
        self.sample_rate = sample_rate
        self.max_duration_s = max_duration_s
        self.idle_stream = idle_stream
        self.pre_roll_ms = pre_roll_ms

        # Preroll ringbuffer (deque): stores chunks, max sample count
        self.pre_roll_max_samples = (pre_roll_ms * sample_rate) // 1000 if pre_roll_ms > 0 else 0
        self.pre_roll_buffer: collections.deque = collections.deque()
        self.pre_roll_total_samples = 0

        # Capture list (only while _capturing is True)
        self.capture_chunks: list[np.ndarray] = []
        self.capture_total_samples = 0

        # See class docstring for the locking rules.
        self._buffer_lock = Lock()
        self._device_lock = Lock()
        # Backward-compat alias (same object as _buffer_lock)
        self.buffer_lock = self._buffer_lock

        self.stream = None
        self._capturing = False
        self.reached_max_duration = False

    def _on_audio(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        """
        Audio callback (sounddevice internal thread).

        Appends chunk to preroll ringbuffer always; if _capturing is True,
        also appends to capture list. Takes only _buffer_lock (never the
        device lock) so device operations can't deadlock against it.
        """
        chunk = indata[:, 0].copy()

        if status:
            # Log status once per unique status string to avoid spam
            status_str = str(status)
            if status_str not in _LAST_STATUS_LOGGED:
                logger.warning(f"Audio callback status: {status}")
                _LAST_STATUS_LOGGED[status_str] = status_str

        with self._buffer_lock:
            # Append to preroll ringbuffer, dropping oldest chunks over the cap
            if self.pre_roll_max_samples > 0:
                self.pre_roll_buffer.append(chunk)
                self.pre_roll_total_samples += len(chunk)
                while self.pre_roll_total_samples > self.pre_roll_max_samples:
                    popped = self.pre_roll_buffer.popleft()
                    self.pre_roll_total_samples -= len(popped)

            # Append to capture list if capturing
            if self._capturing:
                self.capture_chunks.append(chunk)
                self.capture_total_samples += len(chunk)

                # Check if max duration reached (on capture)
                duration_s = self.capture_total_samples / self.sample_rate
                if duration_s >= self.max_duration_s:
                    self.reached_max_duration = True

    def _create_stream(self):
        """Create a new InputStream (callers hold _device_lock)."""
        return sd.InputStream(
            device=self.device,
            channels=1,
            dtype=np.float32,
            samplerate=self.sample_rate,
            callback=self._on_audio,
            blocksize=512,
        )

    def open_stream(self) -> None:
        """
        Open the resident audio stream (SPEC §6.0). Idempotent.

        idle_stream="running": stream is started and left running.
        idle_stream="stopped": stream is started then immediately stopped
        (warms up CoreAudio init and the mic permission prompt at launch,
        but stays stopped while idle).
        May raise on permission/device errors.
        """
        with self._device_lock:
            if self.stream is not None:
                return

            try:
                self.stream = self._create_stream()
                self.stream.start()
                if self.idle_stream == "stopped":
                    self.stream.stop()
                logger.debug(
                    f"Resident audio stream opened (idle_stream={self.idle_stream})"
                )
            except Exception as e:
                logger.error(f"Failed to open resident audio stream: {e}")
                self.stream = None
                raise

    def _ensure_stream_started(self) -> None:
        """
        Device-side preparation for start_recording (callers must NOT hold
        _buffer_lock). Takes _device_lock only.

        - stream is None: (re)create + start.
        - stream inactive, idle_stream="stopped": start() (normal path).
        - stream inactive, idle_stream="running": try start(); on failure
          close the old stream and recreate.
        - stream active: nothing to do (guarded to avoid double-start).
        """
        with self._device_lock:
            if self.stream is not None and self.stream.active:
                return

            if self.stream is None:
                self.stream = self._create_stream()
                self.stream.start()
                logger.warning("Resident stream was missing; reconnected")
                return

            # stream exists but inactive
            if self.idle_stream == "stopped":
                self.stream.start()
                return

            # running mode: unexpected dead stream — try restart, then recreate
            try:
                self.stream.start()
                logger.warning("Resident stream was inactive; restarted")
            except Exception as e:
                logger.warning(f"Restart of dead stream failed ({e}); recreating")
                try:
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None
                self.stream = self._create_stream()
                self.stream.start()
                logger.warning("Resident stream recreated")

    def start_recording(self) -> None:
        """
        Start capturing audio (SPEC §6.0).

        (1) Device preparation under _device_lock (no-op in the common
        running-mode case: the stream is already active).
        (2) Under _buffer_lock: init capture list from preroll (if
        idle_stream=running and pre_roll_ms>0), set _capturing=True.
        Returns in <5ms in running mode. Raises if the device is unusable.
        """
        with self._buffer_lock:
            if self._capturing:
                return

        try:
            self._ensure_stream_started()
        except Exception as e:
            logger.error(f"Failed to start audio stream for recording: {e}")
            with self._device_lock:
                self.stream = None
            raise

        with self._buffer_lock:
            self.capture_chunks = []
            if self.idle_stream == "running" and self.pre_roll_ms > 0:
                # Copy preroll contents (list of chunk references)
                self.capture_chunks = list(self.pre_roll_buffer)
            self.capture_total_samples = sum(len(c) for c in self.capture_chunks)
            self.reached_max_duration = False
            self._capturing = True

        logger.debug("Recording started (capture flag)")

    def stop_recording(self) -> np.ndarray:
        """
        Stop capturing and return accumulated audio.

        Clears the capturing flag and takes the chunk list under
        _buffer_lock, concatenates after releasing it, and (in stopped mode)
        stops the stream under _device_lock last.
        Returns empty array if nothing captured.
        """
        with self._buffer_lock:
            self._capturing = False
            chunks = self.capture_chunks

        result = (
            np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)
        )

        if self.idle_stream == "stopped":
            with self._device_lock:
                try:
                    if self.stream is not None and self.stream.active:
                        self.stream.stop()
                except Exception as e:
                    logger.error(f"Error stopping stream: {e}")

        logger.debug("Recording stopped")
        return result

    def pause_stream(self) -> None:
        """
        Pause the resident stream (for tray "enabled" toggle).

        No-op if idle_stream="stopped". Exceptions logged as WARNING.
        """
        if self.idle_stream == "stopped":
            return

        with self._device_lock:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    logger.debug("Stream paused")
                except Exception as e:
                    logger.warning(f"Error pausing stream: {e}")

    def resume_stream(self) -> None:
        """
        Resume the resident stream (for tray "enabled" toggle).

        No-op if idle_stream="stopped". Exceptions logged as WARNING.
        """
        if self.idle_stream == "stopped":
            return

        with self._device_lock:
            if self.stream is not None:
                try:
                    if not self.stream.active:
                        self.stream.start()
                    logger.debug("Stream resumed")
                except Exception as e:
                    logger.warning(f"Error resuming stream: {e}")

    def close(self) -> None:
        """
        Close the resident stream (e.g., on app exit).

        Stops and closes under _device_lock, then clears buffers/flags under
        _buffer_lock. Safe to call multiple times.
        """
        with self._device_lock:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception as e:
                    logger.error(f"Error closing stream: {e}")
                finally:
                    self.stream = None

        with self._buffer_lock:
            self._capturing = False
            self.capture_chunks = []
            self.capture_total_samples = 0

        logger.debug("Stream closed")

    def get_current_rms(self) -> float:
        """
        Get current RMS level from the most recent audio (~100ms).

        Used for level meter display. Reads from the most recent chunks
        in the capture list (or preroll if not capturing).

        Returns:
            float: RMS level (0-1 scale, approximate)
        """
        window = 1600  # ~100ms @ 16kHz
        with self._buffer_lock:
            chunks = self.capture_chunks if self._capturing else list(self.pre_roll_buffer)
            if not chunks:
                return 0.0
            # Gather recent chunks up to the window size
            recent: list[np.ndarray] = []
            collected = 0
            for chunk in reversed(chunks):
                recent.append(chunk)
                collected += len(chunk)
                if collected >= window:
                    break
            samples = np.concatenate(recent[::-1])[-window:]

        rms = np.sqrt(np.mean(samples ** 2))
        return float(np.clip(rms, 0.0, 1.0))

    def check_max_duration_reached(self) -> bool:
        """
        Check if max recording duration has been reached.

        Returns:
            bool: True if max duration reached
        """
        return self.reached_max_duration
