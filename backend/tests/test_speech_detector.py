"""Unit tests for the speech-detector (VAD) service.

The pure `_frames_to_segments` aggregation is exercised directly with crafted
per-frame flags; the ffmpeg/webrtcvad I/O is only covered via the graceful
degradation path.
"""

from unittest.mock import patch

from services.speech_detector import _frames_to_segments, detect_speech_segments


class TestFramesToSegments:
    # frame_ms=100 throughout for round-number maths.

    def test_empty_input(self):
        assert _frames_to_segments([]) == []

    def test_all_silence(self):
        assert _frames_to_segments([False, False, False], frame_ms=100) == []

    def test_single_run_padded(self):
        # speech at frames 2..5 → raw [200,600); pad 100 → [100,700]
        flags = [False, False, True, True, True, True, False, False]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=100, total_ms=800
        )
        assert segs == [(0.1, 0.7)]

    def test_merge_across_short_silence(self):
        # two runs split by a single 100 ms gap (< min_silence 200) → one segment
        flags = [False, True, True, False, True, True, False]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=100, total_ms=700
        )
        assert len(segs) == 1

    def test_long_silence_not_merged(self):
        # 300 ms gap (>= min_silence 200) keeps them separate
        flags = [True, True, True, False, False, False, True, True, True]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=100, total_ms=900
        )
        assert len(segs) == 2

    def test_drop_too_short(self):
        # a single 100 ms speech blip is below min_speech 250 → dropped
        flags = [False, True, False]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=100, total_ms=300
        )
        assert segs == []

    def test_padding_overlap_remerges(self):
        # gap == min_silence (not merged in step 2), but padding (120+120) bridges
        # it → re-merged into one segment
        flags = [True, True, True, False, False, True, True, True]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=120, total_ms=800
        )
        assert segs == [(0.0, 0.8)]

    def test_padding_clamped_to_bounds(self):
        # padding never pushes below 0 or beyond total_ms
        flags = [True, True, True, True]
        segs = _frames_to_segments(
            flags, frame_ms=100, min_silence_ms=200, min_speech_ms=250, pad_ms=500, total_ms=400
        )
        assert segs == [(0.0, 0.4)]


class TestDetectSpeechSegments:
    def test_returns_empty_when_webrtcvad_missing(self):
        with patch(
            "services.speech_detector._import_webrtcvad", side_effect=ImportError("no webrtcvad")
        ):
            assert detect_speech_segments("/media/x.mkv") == []

    def test_returns_empty_when_decode_fails(self):
        with (
            patch("services.speech_detector._import_webrtcvad"),
            patch(
                "services.speech_detector._decode_pcm",
                side_effect=RuntimeError("ffmpeg boom"),
            ),
        ):
            assert detect_speech_segments("/media/x.mkv") == []
