#!/usr/bin/env python
"""
Performance measurement: Audio start latency with resident stream.

Measures open_stream() → start_recording() latency 10 times.
Expects <5ms per SPEC §15.

Run with: uv run python tests/perf_mic_test.py
"""

import time
import sys

from koekichi.audio import AudioRecorder


def main():
    """Measure start_recording latency with resident stream."""
    recorder = AudioRecorder(
        device=None,
        sample_rate=16000,
        max_duration_s=120,
        idle_stream="running",
        pre_roll_ms=200,
    )

    print("Opening resident audio stream...")
    try:
        recorder.open_stream()
    except PermissionError:
        print("ERROR: Microphone permission denied. Grant in System Settings > Privacy > Microphone")
        print("SKIP")
        return 0
    except Exception as e:
        print(f"ERROR: Could not open stream: {e}")
        print("SKIP")
        return 0

    print("Resident stream opened. Measuring start_recording() latency...")
    print("(target: <5ms per SPEC §15)\n")

    latencies_ms = []
    for i in range(10):
        t_before = time.perf_counter()
        try:
            recorder.start_recording()
        except Exception as e:
            print(f"ERROR on attempt {i+1}: {e}")
            return 1

        t_after = time.perf_counter()
        dt_ms = (t_after - t_before) * 1000.0
        latencies_ms.append(dt_ms)

        # Stop before next start
        recorder.stop_recording()
        print(f"  Attempt {i+1}: {dt_ms:.2f}ms")

    avg_ms = sum(latencies_ms) / len(latencies_ms)
    max_ms = max(latencies_ms)
    min_ms = min(latencies_ms)

    print(f"\nResults:")
    print(f"  Average: {avg_ms:.2f}ms")
    print(f"  Max:     {max_ms:.2f}ms")
    print(f"  Min:     {min_ms:.2f}ms")
    print(f"  Target:  <5ms (SPEC §15)")

    # Deadlock regression check: pause -> resume -> start must complete.
    # (Callbacks fire every 32ms; before the two-lock fix, pause_stream()
    #  holding the buffer lock across stream.stop() could hang.)
    print("\nDeadlock check: pause_stream -> resume_stream -> start_recording ...")
    t0 = time.perf_counter()
    recorder.pause_stream()
    recorder.resume_stream()
    time.sleep(0.1)  # let callbacks run
    recorder.start_recording()
    recorder.stop_recording()
    recorder.close()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  Completed without hang in {dt_ms:.1f}ms")

    if avg_ms < 5.0:
        print("\n✓ PASS: Average latency is <5ms")
        return 0
    else:
        print(f"\n✗ FAIL: Average latency {avg_ms:.2f}ms exceeds 5ms target")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    finally:
        # Cleanup
        pass
