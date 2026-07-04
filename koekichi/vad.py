"""Voice Activity Detection using webrtcvad (SPEC §8-H1)."""

import logging

import numpy as np
import webrtcvad

logger = logging.getLogger(__name__)


def detect_speech_frames(
    audio: np.ndarray,
    sample_rate: int,
    aggressiveness: int = 2,
) -> list[bool]:
    """
    Detect speech frames using webrtcvad.

    Divides audio into 30ms frames and returns list of boolean indicating speech.

    Args:
        audio: float32 ndarray (assumed 16kHz mono, internally converted to int16)
        sample_rate: Sample rate (should be 16000)
        aggressiveness: VAD aggressiveness (0-3, higher = more aggressive)

    Returns:
        list[bool]: One boolean per 30ms frame (True = speech detected)

    Raises:
        ValueError: If audio is not 16kHz
    """
    if sample_rate != 16000:
        raise ValueError(f"Only 16kHz supported, got {sample_rate}")

    # Initialize VAD (aggressiveness 0-3)
    vad = webrtcvad.Vad(aggressiveness)

    # Convert float32 to int16
    # Clip to [-1, 1] then scale to int16 range
    audio_clipped = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_clipped * 32767).astype(np.int16)

    # Frame size: 30ms @ 16kHz = 480 samples
    frame_size = 480  # 16000 * 0.03
    num_frames = len(audio_int16) // frame_size

    speech_frames = []
    for i in range(num_frames):
        frame = audio_int16[i * frame_size : (i + 1) * frame_size]
        if len(frame) < frame_size:
            break
        is_speech = vad.is_speech(frame.tobytes(), sample_rate)
        speech_frames.append(is_speech)

    return speech_frames


def trim_and_validate_audio(
    audio: np.ndarray,
    sample_rate: int,
    min_speech_ms: int = 300,
    pad_ms: int = 200,
    aggressiveness: int = 2,
    min_speech_ratio: float = 0.10,
) -> tuple[np.ndarray, bool]:
    """
    Validate audio has sufficient speech and trim silence from edges (SPEC §8-H1, §8-H1b).

    If total detected speech is less than min_speech_ms, returns (empty_array, False).
    For recordings longer than RATIO_GATE_MIN_DURATION_MS, additionally checks that
    the speech ratio meets min_speech_ratio; otherwise returns (empty_array, False).
    Otherwise, trims leading/trailing silence (keeping pad_ms on each side) and
    returns (trimmed_audio, True).

    Args:
        audio: float32 ndarray, 16kHz mono
        sample_rate: Sample rate (16000)
        min_speech_ms: Minimum speech duration in ms (default 300)
        pad_ms: Padding to keep on each side when trimming (default 200)
        aggressiveness: VAD aggressiveness 0-3
        min_speech_ratio: Minimum speech ratio for long recordings (default 0.10, SPEC §8-H1b)

    Returns:
        tuple: (trimmed_audio, is_valid)
            - trimmed_audio: audio with silence trimmed (or empty if invalid)
            - is_valid: True if audio has sufficient speech
    """
    # Implementation constant: apply ratio gate only to recordings longer than this
    RATIO_GATE_MIN_DURATION_MS = 3000

    # Detect speech frames
    frames = detect_speech_frames(audio, sample_rate, aggressiveness)

    if not frames:
        return np.array([], dtype=np.float32), False

    # Calculate total speech time
    frame_duration_ms = 30
    total_speech_ms = sum(frames) * frame_duration_ms

    if total_speech_ms < min_speech_ms:
        logger.debug(f"Speech duration {total_speech_ms}ms < min {min_speech_ms}ms")
        return np.array([], dtype=np.float32), False

    # H1b: Apply speech ratio gate for long recordings (SPEC §8-H1b)
    total_duration_ms = len(audio) / sample_rate * 1000.0
    if total_duration_ms > RATIO_GATE_MIN_DURATION_MS:
        speech_ratio = total_speech_ms / total_duration_ms
        if speech_ratio < min_speech_ratio:
            logger.debug(
                f"Speech ratio {speech_ratio:.3f} < min {min_speech_ratio:.3f} "
                f"(total {total_duration_ms:.0f}ms > {RATIO_GATE_MIN_DURATION_MS}ms)"
            )
            return np.array([], dtype=np.float32), False

    # Find first and last speech frame
    first_speech_frame = next((i for i, v in enumerate(frames) if v), None)
    last_speech_frame = next((i for i in range(len(frames) - 1, -1, -1) if frames[i]), None)

    if first_speech_frame is None or last_speech_frame is None:
        return np.array([], dtype=np.float32), False

    # Convert frame indices to sample positions
    frame_samples = 480  # 30ms @ 16kHz
    first_sample = max(0, first_speech_frame * frame_samples - pad_ms * 16)  # pad_ms in samples
    last_sample = min(len(audio), (last_speech_frame + 1) * frame_samples + pad_ms * 16)

    trimmed = audio[first_sample:last_sample]
    return trimmed, True
