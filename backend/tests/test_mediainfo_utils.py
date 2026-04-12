"""Tests for mediainfo_utils module.

Covers: run_mediainfo, _normalize_mediainfo, _map_codec, _normalize_language,
_is_mediainfo_available.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from mediainfo_utils import (
    MEDIAINFO_CODEC_MAP,
    _map_codec,
    _normalize_language,
    _normalize_mediainfo,
    run_mediainfo,
)


# ---------------------------------------------------------------------------
# _map_codec
# ---------------------------------------------------------------------------


class TestMapCodec:
    @pytest.mark.parametrize(
        "input_fmt,expected",
        [
            ("ASS", "ass"),
            ("ass", "ass"),
            ("Advanced SubStation Alpha", "ass"),
            ("SubStation Alpha", "ssa"),
            ("SSA", "ssa"),
            ("UTF-8", "subrip"),
            ("SubRip", "subrip"),
            ("SRT", "subrip"),
            ("VobSub", "dvd_subtitle"),
            ("PGS", "hdmv_pgs_subtitle"),
            ("PGSSub", "hdmv_pgs_subtitle"),
            ("WebVTT", "webvtt"),
            ("Timed Text", "mov_text"),
            ("AAC", "aac"),
            ("AC-3", "ac3"),
            ("E-AC-3", "eac3"),
            ("DTS", "dts"),
            ("DTS-HD MA", "dts"),
            ("TrueHD", "truehd"),
            ("FLAC", "flac"),
            ("MP3", "mp3"),
            ("Opus", "opus"),
            ("Vorbis", "vorbis"),
            ("PCM", "pcm_s16le"),
        ],
    )
    def test_known_codec_mappings(self, input_fmt, expected):
        assert _map_codec(input_fmt) == expected

    def test_unknown_codec_passthrough(self):
        """Unknown format falls back to lowercase original."""
        assert _map_codec("SomeNewCodec") == "somenewcodec"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        assert _map_codec("  ASS  ") == "ass"

    def test_empty_string(self):
        assert _map_codec("") == ""


# ---------------------------------------------------------------------------
# _normalize_language
# ---------------------------------------------------------------------------


class TestNormalizeLanguage:
    def test_lowercase(self):
        assert _normalize_language("ENG") == "eng"

    def test_strip_whitespace(self):
        assert _normalize_language("  jpn  ") == "jpn"

    def test_two_letter_code(self):
        assert _normalize_language("en") == "en"

    def test_full_name(self):
        assert _normalize_language("English") == "english"

    def test_empty(self):
        assert _normalize_language("") == ""


# ---------------------------------------------------------------------------
# _normalize_mediainfo
# ---------------------------------------------------------------------------


class TestNormalizeMediainfo:
    def test_empty_tracks(self):
        raw = {"media": {"track": []}}
        result = _normalize_mediainfo(raw)
        assert result == {"streams": []}

    def test_skips_general_and_video(self):
        """General and Video tracks are skipped."""
        raw = {
            "media": {
                "track": [
                    {"@type": "General", "Format": "Matroska"},
                    {"@type": "Video", "Format": "HEVC"},
                ]
            }
        }
        result = _normalize_mediainfo(raw)
        assert result == {"streams": []}

    def test_audio_track(self):
        raw = {
            "media": {
                "track": [
                    {
                        "@type": "Audio",
                        "Format": "AAC",
                        "Language": "jpn",
                        "Title": "Japanese Stereo",
                    }
                ]
            }
        }
        result = _normalize_mediainfo(raw)
        assert len(result["streams"]) == 1
        stream = result["streams"][0]
        assert stream["codec_type"] == "audio"
        assert stream["codec_name"] == "aac"
        assert stream["index"] == 0
        assert stream["tags"]["language"] == "jpn"
        assert stream["tags"]["title"] == "Japanese Stereo"
        assert stream["disposition"] == {}

    def test_subtitle_track_not_forced(self):
        raw = {
            "media": {
                "track": [
                    {
                        "@type": "Text",
                        "Format": "ASS",
                        "Language": "eng",
                        "Title": "English Full",
                        "Forced": "No",
                    }
                ]
            }
        }
        result = _normalize_mediainfo(raw)
        stream = result["streams"][0]
        assert stream["codec_type"] == "subtitle"
        assert stream["codec_name"] == "ass"
        assert stream["disposition"]["forced"] == 0

    def test_subtitle_track_forced(self):
        raw = {
            "media": {
                "track": [
                    {
                        "@type": "Text",
                        "Format": "ASS",
                        "Language": "eng",
                        "Title": "Signs/Songs",
                        "Forced": "Yes",
                    }
                ]
            }
        }
        result = _normalize_mediainfo(raw)
        stream = result["streams"][0]
        assert stream["disposition"]["forced"] == 1

    def test_mixed_tracks_indexing(self):
        """Audio and Text tracks get sequential indices (General/Video skipped)."""
        raw = {
            "media": {
                "track": [
                    {"@type": "General"},
                    {"@type": "Video"},
                    {"@type": "Audio", "Format": "AAC", "Language": "jpn"},
                    {"@type": "Audio", "Format": "AC-3", "Language": "eng"},
                    {"@type": "Text", "Format": "ASS", "Language": "jpn", "Forced": "No"},
                    {"@type": "Text", "Format": "SRT", "Language": "eng", "Forced": "No"},
                ]
            }
        }
        result = _normalize_mediainfo(raw)
        assert len(result["streams"]) == 4
        assert result["streams"][0]["index"] == 0
        assert result["streams"][0]["codec_type"] == "audio"
        assert result["streams"][1]["index"] == 1
        assert result["streams"][1]["codec_type"] == "audio"
        assert result["streams"][2]["index"] == 2
        assert result["streams"][2]["codec_type"] == "subtitle"
        assert result["streams"][3]["index"] == 3
        assert result["streams"][3]["codec_type"] == "subtitle"

    def test_missing_language(self):
        """Missing Language field defaults to empty string."""
        raw = {"media": {"track": [{"@type": "Audio", "Format": "AAC"}]}}
        result = _normalize_mediainfo(raw)
        assert result["streams"][0]["tags"]["language"] == ""

    def test_missing_title(self):
        """Missing Title field defaults to empty string."""
        raw = {"media": {"track": [{"@type": "Audio", "Format": "AAC"}]}}
        result = _normalize_mediainfo(raw)
        assert result["streams"][0]["tags"]["title"] == ""

    def test_missing_forced(self):
        """Missing Forced field defaults to not forced."""
        raw = {"media": {"track": [{"@type": "Text", "Format": "ASS"}]}}
        result = _normalize_mediainfo(raw)
        assert result["streams"][0]["disposition"]["forced"] == 0

    def test_empty_media(self):
        raw = {"media": {}}
        result = _normalize_mediainfo(raw)
        assert result == {"streams": []}

    def test_no_media_key(self):
        raw = {}
        result = _normalize_mediainfo(raw)
        assert result == {"streams": []}


# ---------------------------------------------------------------------------
# run_mediainfo
# ---------------------------------------------------------------------------


class TestRunMediainfo:
    @patch("mediainfo_utils._is_mediainfo_available", return_value=False)
    def test_mediainfo_not_available(self, _mock):
        with pytest.raises(FileNotFoundError, match="mediainfo not found"):
            run_mediainfo("/some/video.mkv")

    @patch("mediainfo_utils._is_mediainfo_available", return_value=True)
    @patch("mediainfo_utils.subprocess.run")
    def test_successful_run(self, mock_run, _avail):
        raw_output = {
            "media": {
                "track": [
                    {"@type": "Audio", "Format": "AAC", "Language": "jpn"},
                ]
            }
        }
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps(raw_output), stderr=""
        )
        result = run_mediainfo("/video.mkv")
        assert len(result["streams"]) == 1
        assert result["streams"][0]["codec_name"] == "aac"

    @patch("mediainfo_utils._is_mediainfo_available", return_value=True)
    @patch("mediainfo_utils.subprocess.run")
    def test_nonzero_exit(self, mock_run, _avail):
        mock_run.return_value = MagicMock(returncode=1, stderr="error msg")
        with pytest.raises(RuntimeError, match="mediainfo failed"):
            run_mediainfo("/video.mkv")

    @patch("mediainfo_utils._is_mediainfo_available", return_value=True)
    @patch("mediainfo_utils.subprocess.run", side_effect=subprocess.TimeoutExpired("mediainfo", 30))
    def test_timeout(self, _run, _avail):
        with pytest.raises(RuntimeError, match="timed out"):
            run_mediainfo("/video.mkv")

    @patch("mediainfo_utils._is_mediainfo_available", return_value=True)
    @patch("mediainfo_utils.subprocess.run")
    def test_invalid_json(self, mock_run, _avail):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with pytest.raises(RuntimeError, match="invalid JSON"):
            run_mediainfo("/video.mkv")
