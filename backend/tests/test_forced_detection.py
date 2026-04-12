"""Tests for forced_detection module.

Covers: detect_subtitle_type (multi-signal), is_forced_external_sub,
classify_forced_result, SUBTITLE_TYPES constant.
"""

import pytest

from forced_detection import (
    SUBTITLE_TYPES,
    classify_forced_result,
    detect_subtitle_type,
    is_forced_external_sub,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_subtitle_types_contains_expected(self):
        assert "full" in SUBTITLE_TYPES
        assert "forced" in SUBTITLE_TYPES
        assert "signs" in SUBTITLE_TYPES

    def test_subtitle_types_length(self):
        assert len(SUBTITLE_TYPES) == 3


# ---------------------------------------------------------------------------
# detect_subtitle_type — single signals
# ---------------------------------------------------------------------------


class TestDetectSubtitleTypeSingleSignals:
    def test_no_signals_returns_full(self):
        """No arguments at all -> full with confidence 1.0."""
        stype, conf = detect_subtitle_type()
        assert stype == "full"
        assert conf == 1.0

    def test_disposition_forced(self):
        """ffprobe disposition.forced=1 -> forced, confidence 1.0."""
        stream = {"disposition": {"forced": 1}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "forced"
        assert conf == 1.0

    def test_disposition_not_forced(self):
        """disposition.forced=0 -> no signal, falls through to full."""
        stream = {"disposition": {"forced": 0}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "full"
        assert conf == 1.0

    def test_disposition_missing(self):
        """No disposition key -> no signal."""
        stream = {"tags": {"language": "eng"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "full"
        assert conf == 1.0

    def test_filename_forced(self):
        """.forced. in filename -> forced, 0.9."""
        stype, conf = detect_subtitle_type(file_path="/media/show.forced.srt")
        assert stype == "forced"
        assert conf == 0.9

    def test_filename_foreign(self):
        """.foreign. in filename -> forced, 0.9."""
        stype, conf = detect_subtitle_type(file_path="/media/show.foreign.ass")
        assert stype == "forced"
        assert conf == 0.9

    def test_filename_signs(self):
        """.signs. in filename -> signs, 0.9."""
        stype, conf = detect_subtitle_type(file_path="/media/show.signs.srt")
        assert stype == "signs"
        assert conf == 0.9

    def test_filename_sign_singular(self):
        """.sign. in filename -> signs, 0.9."""
        stype, conf = detect_subtitle_type(file_path="/media/show.sign.ass")
        assert stype == "signs"
        assert conf == 0.9

    def test_stream_title_forced(self):
        """Stream title containing 'forced' -> forced, 0.8."""
        stream = {"tags": {"title": "English (Forced)"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "forced"
        assert conf == 0.8

    def test_stream_title_foreign(self):
        """Stream title containing 'foreign' -> forced, 0.8."""
        stream = {"tags": {"title": "Foreign Parts Only"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "forced"
        assert conf == 0.8

    def test_stream_title_sign(self):
        """Stream title containing 'sign' -> signs, 0.8."""
        stream = {"tags": {"title": "Signs/Songs"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "signs"
        assert conf == 0.8

    def test_stream_title_song(self):
        """Stream title containing 'song' -> signs, 0.8."""
        stream = {"tags": {"title": "Songs Only"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "signs"
        assert conf == 0.8

    def test_empty_stream_info(self):
        """Empty stream_info dict -> full."""
        stype, conf = detect_subtitle_type(stream_info={})
        assert stype == "full"
        assert conf == 1.0

    def test_stream_title_none(self):
        """tags.title is None -> no signal."""
        stream = {"tags": {"title": None}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "full"

    def test_tags_not_dict(self):
        """tags is not a dict -> no signal from title."""
        stream = {"tags": "invalid"}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "full"

    def test_disposition_not_dict(self):
        """disposition is not a dict -> no signal."""
        stream = {"disposition": "invalid"}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "full"


# ---------------------------------------------------------------------------
# detect_subtitle_type — multi-signal agreement
# ---------------------------------------------------------------------------


class TestDetectSubtitleTypeMultiSignal:
    def test_disposition_plus_filename_forced(self):
        """Two forced signals -> forced with highest confidence."""
        stream = {"disposition": {"forced": 1}}
        stype, conf = detect_subtitle_type(
            stream_info=stream, file_path="/media/show.forced.srt"
        )
        assert stype == "forced"
        assert conf == 1.0  # highest confidence from disposition

    def test_filename_plus_title_signs(self):
        """Filename signs + title sign -> signs with 0.9 (filename confidence)."""
        stream = {"tags": {"title": "Signs/Songs"}}
        stype, conf = detect_subtitle_type(
            stream_info=stream, file_path="/media/show.signs.srt"
        )
        assert stype == "signs"
        assert conf == 0.9

    def test_mixed_signals_forced_wins_by_count(self):
        """Disposition forced + title forced -> forced wins by count."""
        stream = {"disposition": {"forced": 1}, "tags": {"title": "Forced"}}
        stype, conf = detect_subtitle_type(stream_info=stream)
        assert stype == "forced"
        assert conf == 1.0

    def test_filename_forced_and_signs(self):
        """Filename with both .forced. and .signs. -> both signals, single signal each."""
        stype, conf = detect_subtitle_type(
            file_path="/media/show.forced.signs.srt"
        )
        # Both forced and signs get one signal each, highest confidence wins
        assert stype in ("forced", "signs")
        assert conf == 0.9

    def test_ass_signs_only_styles(self):
        """ASS with only signs styles -> signs, 0.7."""
        mock_ass = type("SSAFile", (), {"styles": {}})()
        import unittest.mock as mock

        with mock.patch("ass_utils.classify_styles") as m:
            # No dialog styles, only signs styles
            m.return_value = ([], ["Sign", "Title"])
            stype, conf = detect_subtitle_type(ass_content=mock_ass)
            assert stype == "signs"
            assert conf == 0.7

    def test_ass_with_dialog_styles(self):
        """ASS with dialog styles -> not signs from ASS signal."""
        mock_ass = type("SSAFile", (), {"styles": {}})()
        import unittest.mock as mock

        with mock.patch("ass_utils.classify_styles") as m:
            m.return_value = (["Default", "Main"], ["Sign"])
            stype, conf = detect_subtitle_type(ass_content=mock_ass)
            assert stype == "full"
            assert conf == 1.0

    def test_ass_classify_exception(self):
        """classify_styles raises -> no ASS signal, no crash."""
        mock_ass = type("SSAFile", (), {"styles": {}})()
        import unittest.mock as mock

        with mock.patch(
            "ass_utils.classify_styles", side_effect=Exception("parse error")
        ):
            stype, conf = detect_subtitle_type(ass_content=mock_ass)
            assert stype == "full"
            assert conf == 1.0


# ---------------------------------------------------------------------------
# is_forced_external_sub
# ---------------------------------------------------------------------------


class TestIsForcedExternalSub:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/media/show.forced.srt", True),
            ("/media/show.forced.ass", True),
            ("/media/show.signs.srt", True),
            ("/media/show.sign.ass", True),
            ("/media/show.foreign.vtt", True),
            ("/media/show.forced.ssa", True),
            ("/media/show.en.srt", False),
            ("/media/show.srt", False),
            ("/media/show.de.ass", False),
            ("/media/forced/show.srt", False),  # forced in dir, not filename
        ],
    )
    def test_filename_patterns(self, path, expected):
        assert is_forced_external_sub(path) == expected

    def test_case_insensitive(self):
        """Regex is case-insensitive."""
        assert is_forced_external_sub("/media/show.FORCED.SRT")
        assert is_forced_external_sub("/media/show.Signs.Ass")


# ---------------------------------------------------------------------------
# classify_forced_result
# ---------------------------------------------------------------------------


class TestClassifyForcedResult:
    def test_provider_foreign_parts_only(self):
        """OpenSubtitles foreign_parts_only -> forced."""
        assert classify_forced_result("test.srt", {"foreign_parts_only": True}) == "forced"

    def test_provider_not_foreign(self):
        """foreign_parts_only=False -> check filename."""
        assert classify_forced_result("test.srt", {"foreign_parts_only": False}) == "full"

    def test_empty_filename(self):
        """Empty filename -> full."""
        assert classify_forced_result("", None) == "full"

    def test_none_provider_data(self):
        """None provider_data -> check filename only."""
        assert classify_forced_result("test.srt", None) == "full"

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("show.forced.srt", "forced"),
            ("show.foreign.srt", "forced"),
            ("show.signs.srt", "signs"),
            ("show.sign.srt", "signs"),
            ("[Sub] Show - 01 (Signs & Songs).ass", "signs"),
            ("[Sub] Show - 01 (signs only).srt", "signs"),
            ("show.forced.ass", "forced"),
            ("show.en.srt", "full"),
            ("regular_subtitle.srt", "full"),
        ],
    )
    def test_filename_classification(self, filename, expected):
        assert classify_forced_result(filename) == expected

    def test_signs_and_songs_pattern(self):
        """signs & songs pattern -> signs."""
        assert classify_forced_result("[Group] Show - 01 (Signs & Songs).ass") == "signs"

    def test_forced_keyword_in_name(self):
        """'forced' keyword as standalone word -> forced."""
        assert classify_forced_result("show forced eng.srt") == "forced"

    def test_forced_in_underscore_context(self):
        """'forced' surrounded by underscores is a word char boundary — not matched."""
        assert classify_forced_result("show_forced_eng.srt") == "full"
