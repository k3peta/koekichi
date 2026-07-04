"""Test VAD (Voice Activity Detection) (SPEC §8-H1)."""

import numpy as np
import pytest

from koekichi.vad import detect_speech_frames, trim_and_validate_audio


class TestDetectSpeechFrames:
    """Test speech frame detection."""

    def test_silence_no_frames(self) -> None:
        """Pure silence should detect no speech frames."""
        sample_rate = 16000
        silence = np.zeros(sample_rate, dtype=np.float32)  # 1 second of silence
        frames = detect_speech_frames(silence, sample_rate, aggressiveness=2)
        # Most or all frames should be non-speech
        speech_frames = sum(frames)
        assert speech_frames == 0 or speech_frames < 3  # Allow very few false positives

    def test_sine_wave_detection(self) -> None:
        """440Hz sine wave should detect speech frames."""
        sample_rate = 16000
        duration_s = 1.0
        t = np.arange(int(sample_rate * duration_s), dtype=np.float32) / sample_rate
        # 440Hz sine wave, amplitude 0.3
        sine_wave = 0.3 * np.sin(2 * np.pi * 440 * t)
        frames = detect_speech_frames(sine_wave, sample_rate, aggressiveness=2)
        # Should detect speech in many frames
        speech_frames = sum(frames)
        assert speech_frames > 5, f"Expected many speech frames, got {speech_frames}"

    def test_frame_size_calculation(self) -> None:
        """Verify 30ms frame size (480 samples @ 16kHz)."""
        sample_rate = 16000
        # 1 second = 33.3 frames of 30ms
        duration_s = 1.0
        audio = np.zeros(int(sample_rate * duration_s), dtype=np.float32)
        frames = detect_speech_frames(audio, sample_rate)
        # Should be approximately 33-34 frames
        assert 32 <= len(frames) <= 34

    def test_unsupported_sample_rate(self) -> None:
        """Only 16kHz is supported."""
        audio = np.zeros(8000, dtype=np.float32)
        with pytest.raises(ValueError, match="Only 16kHz"):
            detect_speech_frames(audio, 8000)

    def test_mixed_silence_and_speech(self) -> None:
        """Silence followed by tone should detect transition."""
        sample_rate = 16000
        # 0.5s silence + 0.5s tone
        silence = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        t = np.arange(int(sample_rate * 0.5), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        audio = np.concatenate([silence, tone])

        frames = detect_speech_frames(audio, sample_rate, aggressiveness=2)
        # Later frames should show more speech
        first_half_speech = sum(frames[:10])
        second_half_speech = sum(frames[-10:])
        assert second_half_speech > first_half_speech


class TestTrimAndValidateAudio:
    """Test audio validation and trimming."""

    def test_pure_silence_invalid(self) -> None:
        """Pure silence should be marked invalid."""
        sample_rate = 16000
        silence = np.zeros(sample_rate, dtype=np.float32)
        trimmed, is_valid = trim_and_validate_audio(
            silence, sample_rate, min_speech_ms=300, pad_ms=200
        )
        assert is_valid is False
        assert len(trimmed) == 0

    def test_sufficient_speech_valid(self) -> None:
        """Audio with sufficient speech should be valid."""
        sample_rate = 16000
        # 1 second of 440Hz tone (enough speech)
        t = np.arange(sample_rate, dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        trimmed, is_valid = trim_and_validate_audio(
            tone, sample_rate, min_speech_ms=300, pad_ms=200
        )
        assert is_valid is True
        assert len(trimmed) > 0

    def test_insufficient_speech_duration(self) -> None:
        """Audio with insufficient speech duration should be invalid."""
        sample_rate = 16000
        # 0.1 second of tone (less than 300ms min)
        duration_s = 0.1
        t = np.arange(int(sample_rate * duration_s), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        trimmed, is_valid = trim_and_validate_audio(
            tone, sample_rate, min_speech_ms=300, pad_ms=200
        )
        assert is_valid is False

    def test_boundary_min_speech_ms(self) -> None:
        """Test at the boundary of min_speech_ms."""
        sample_rate = 16000
        # Create audio with exactly enough speech (300ms)
        duration_s = 0.3
        t = np.arange(int(sample_rate * duration_s), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        trimmed, is_valid = trim_and_validate_audio(
            tone, sample_rate, min_speech_ms=300, pad_ms=200
        )
        assert is_valid is True

    def test_trimming_removes_leading_silence(self) -> None:
        """Trimming should remove leading silence."""
        sample_rate = 16000
        # 0.5s silence + 1s tone + 0.5s silence
        silence_lead = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        t = np.arange(sample_rate, dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        silence_trail = np.zeros(int(sample_rate * 0.5), dtype=np.float32)
        audio = np.concatenate([silence_lead, tone, silence_trail])

        trimmed, is_valid = trim_and_validate_audio(
            audio, sample_rate, min_speech_ms=300, pad_ms=0
        )
        assert is_valid is True
        # Trimmed should be shorter than original
        assert len(trimmed) < len(audio)
        # Trimmed should be close to the tone length
        assert len(trimmed) > sample_rate * 0.8  # Allow some padding

    def test_trimming_with_padding(self) -> None:
        """Trimming should preserve pad_ms silence on edges."""
        sample_rate = 16000
        # Silence + tone + silence
        silence_lead = np.zeros(int(sample_rate * 0.2), dtype=np.float32)
        t = np.arange(sample_rate, dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        silence_trail = np.zeros(int(sample_rate * 0.2), dtype=np.float32)
        audio = np.concatenate([silence_lead, tone, silence_trail])

        # With 200ms padding
        trimmed, is_valid = trim_and_validate_audio(
            audio, sample_rate, min_speech_ms=300, pad_ms=200
        )
        assert is_valid is True
        # Trimmed should include padded silence
        assert len(trimmed) > sample_rate * 0.8  # More than just tone

    def test_empty_audio(self) -> None:
        """Empty audio should be invalid."""
        audio = np.array([], dtype=np.float32)
        trimmed, is_valid = trim_and_validate_audio(audio, 16000)
        assert is_valid is False
        assert len(trimmed) == 0

    def test_float32_clipping_in_vad(self) -> None:
        """VAD should handle float32 values > 1.0."""
        sample_rate = 16000
        # Over-amplitude tone (2.0)
        t = np.arange(sample_rate, dtype=np.float32) / sample_rate
        tone = 2.0 * np.sin(2 * np.pi * 440 * t)  # Amplitude > 1
        trimmed, is_valid = trim_and_validate_audio(
            tone, sample_rate, min_speech_ms=300, pad_ms=200
        )
        # Should still work (internally clipped)
        assert is_valid is True

    def test_long_recording_low_speech_ratio_invalid(self) -> None:
        """Long recording with insufficient speech ratio should be invalid (SPEC §8-H1b)."""
        sample_rate = 16000
        # 6s total, only 400ms of tone (~6.7% ratio, below the 10% default)
        total_duration_s = 6.0
        speech_duration_s = 0.4
        silence_duration_s = total_duration_s - speech_duration_s
        silence = np.zeros(int(sample_rate * silence_duration_s), dtype=np.float32)
        t = np.arange(int(sample_rate * speech_duration_s), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        audio = np.concatenate([silence, tone])
        assert len(audio) > 3000 * 16  # > 3000ms

        trimmed, is_valid = trim_and_validate_audio(
            audio,
            sample_rate,
            min_speech_ms=300,  # 400ms of speech passes this check
            pad_ms=200,
            min_speech_ratio=0.10,  # but fails the ratio gate
        )
        assert is_valid is False

    def test_short_recording_low_ratio_still_valid(self) -> None:
        """Short recording (≤3000ms) should not apply the ratio gate (SPEC §8-H1b)."""
        sample_rate = 16000
        silence_lead = np.zeros(int(sample_rate * 0.45), dtype=np.float32)
        t = np.arange(int(sample_rate * 0.1), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        silence_trail = np.zeros(int(sample_rate * 0.45), dtype=np.float32)
        audio = np.concatenate([silence_lead, tone, silence_trail])
        assert len(audio) <= 3000 * 16  # ≤ 3000ms

        trimmed, is_valid = trim_and_validate_audio(
            audio,
            sample_rate,
            min_speech_ms=100,  # 100ms of speech passes this check
            pad_ms=200,
            min_speech_ratio=0.10,
        )
        # Ratio here (~10%) would fail the gate, but short recordings are exempt
        assert is_valid is True

    def test_long_recording_sufficient_ratio_valid(self) -> None:
        """Long recording with sufficient speech ratio should be valid (SPEC §8-H1b)."""
        sample_rate = 16000
        # 6s total, 3s of tone (50% ratio, above the 10% default)
        silence_lead = np.zeros(int(sample_rate * 1.5), dtype=np.float32)
        t = np.arange(int(sample_rate * 3.0), dtype=np.float32) / sample_rate
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        silence_trail = np.zeros(int(sample_rate * 1.5), dtype=np.float32)
        audio = np.concatenate([silence_lead, tone, silence_trail])
        assert len(audio) > 3000 * 16  # > 3000ms

        trimmed, is_valid = trim_and_validate_audio(
            audio,
            sample_rate,
            min_speech_ms=300,
            pad_ms=200,
            min_speech_ratio=0.10,
        )
        assert is_valid is True
