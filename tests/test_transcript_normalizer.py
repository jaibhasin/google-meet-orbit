from __future__ import annotations

import unittest

from orbit.transcript import TranscriptSegment
from orbit.transcript_normalizer import normalize_transcript_segments, normalize_transcript_text


class TranscriptNormalizerTests(unittest.TestCase):
    def test_filler_only_segment_is_dropped(self):
        segments = normalize_transcript_segments(
            "abc-defg-hij",
            [
                TranscriptSegment(
                    source_id="segment-0001",
                    raw_text="um",
                    clean_text="um",
                    memory_text="um",
                )
            ],
        )

        self.assertEqual(segments, [])

    def test_repeated_prefix_is_cleaned(self):
        normalized = normalize_transcript_text("launch launch launch next friday")
        self.assertEqual(normalized, "Launch next friday.")

    def test_memory_text_includes_speaker_and_timestamps(self):
        segments = normalize_transcript_segments(
            "abc-defg-hij",
            [
                TranscriptSegment(
                    source_id="segment-0002",
                    raw_text="we should ship after qa signs off",
                    clean_text="",
                    memory_text="",
                    speaker_label="Jai",
                    speaker_confidence="caption_dom",
                    start_ms=12_000,
                    end_ms=18_000,
                )
            ],
        )

        self.assertEqual(len(segments), 1)
        self.assertEqual(
            segments[0].memory_text,
            "Meet abc-defg-hij transcript - Jai - 00:00:12-00:00:18: We should ship after qa signs off.",
        )


if __name__ == "__main__":
    unittest.main()
