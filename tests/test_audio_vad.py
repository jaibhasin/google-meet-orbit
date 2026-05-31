from __future__ import annotations

import math
import struct
import unittest

from orbit.audio_vad import PCM16SilenceGate, is_pcm16_silent, pcm16_rms


SAMPLE_RATE = 16000


def pcm_chunk(amplitude: int, duration_ms: int = 100, frequency_hz: int = 440) -> bytes:
    samples = []
    for index in range(SAMPLE_RATE * duration_ms // 1000):
        value = int(amplitude * math.sin(2 * math.pi * frequency_hz * index / SAMPLE_RATE))
        samples.append(value)
    return struct.pack(f"<{len(samples)}h", *samples)


class AudioVadTests(unittest.TestCase):
    def test_pcm16_rms_detects_zero_chunk(self):
        chunk = pcm_chunk(0)

        self.assertEqual(pcm16_rms(chunk), 0)
        self.assertTrue(is_pcm16_silent(chunk, threshold=400))

    def test_pcm16_rms_detects_non_silent_sine_chunk(self):
        chunk = pcm_chunk(2000)

        self.assertGreater(pcm16_rms(chunk), 1000)
        self.assertFalse(is_pcm16_silent(chunk, threshold=400))

    def test_first_silent_chunk_is_buffered_not_dropped(self):
        gate = PCM16SilenceGate(sample_rate=SAMPLE_RATE)

        result = gate.process(pcm_chunk(0))

        self.assertEqual(result.chunks_to_forward, ())
        self.assertEqual(result.dropped_silence_bytes, 0)
        self.assertFalse(result.silence_gated)

    def test_speech_flushes_pre_roll(self):
        gate = PCM16SilenceGate(sample_rate=SAMPLE_RATE)
        silence = pcm_chunk(0)
        speech = pcm_chunk(2000)

        gate.process(silence)
        gate.process(silence)
        result = gate.process(speech)

        self.assertEqual(result.chunks_to_forward, (silence, silence, speech))
        self.assertFalse(result.is_silent)

    def test_post_roll_is_forwarded_after_speech(self):
        gate = PCM16SilenceGate(sample_rate=SAMPLE_RATE)
        speech = pcm_chunk(2000)
        silence = pcm_chunk(0)

        gate.process(speech)
        results = [gate.process(silence) for _ in range(9)]

        self.assertTrue(all(result.chunks_to_forward == (silence,) for result in results))

    def test_sustained_silence_is_dropped(self):
        gate = PCM16SilenceGate(sample_rate=SAMPLE_RATE)
        silence = pcm_chunk(0)

        results = [gate.process(silence) for _ in range(16)]

        self.assertTrue(results[-1].silence_gated)
        self.assertGreater(sum(result.dropped_silence_bytes for result in results), 0)
        self.assertEqual(results[-1].chunks_to_forward, ())


if __name__ == "__main__":
    unittest.main()
