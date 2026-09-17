"""Regression: no writer may put a subtitle on disk under a raw ISO 639-2 tag.

e9ef92d5 canonicalised the automatic extractor (``ger`` -> ``de``), but three
more entry points still spliced the raw tag into the filename, so ``.ger.srt``
kept growing next to ``.de.srt`` (prod: 2 849 alias duplicates):

* ``POST /library/episodes/<id>/tracks/<index>/extract``
* ``POST /library/series/<id>/batch-extract-tracks`` — which then also removes
  the track from the container, so the duplicate is not even reproducible
* manual upload, whose conflict check compared ``ger`` against ``de`` literally
  and let a second German subtitle through
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from services.subtitle_upload import UploadError, save_manual_subtitle

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"

_STREAMS = [
    {"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {}},
    {
        "index": 1,
        "codec_type": "subtitle",
        "codec_name": "subrip",
        "tags": {"language": "ger"},
        "disposition": {"default": 0, "forced": 0},
    },
]


class TestSingleTrackExtract:
    def test_raw_container_tag_is_written_canonical(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"v")
        with (
            patch("routes.tracks._get_video_path", return_value=str(video)),
            patch("routes.tracks.get_media_streams", return_value={"streams": _STREAMS}),
            patch("routes.tracks.extract_subtitle_stream") as mock_ext,
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/1/extract", json={})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["output_path"].endswith("ep.de.srt")
        assert mock_ext.call_args.args[2].endswith("ep.de.srt")

    def test_explicit_language_from_the_ui_is_canonicalised_too(self, client, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"v")
        with (
            patch("routes.tracks._get_video_path", return_value=str(video)),
            patch("routes.tracks.get_media_streams", return_value={"streams": _STREAMS}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post(
                "/api/v1/library/episodes/1/tracks/1/extract", json={"language": "eng"}
            )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["language"] == "en"


class TestTrackSidecarPath:
    """The naming helper both track-extraction routes build their output with."""

    def test_raw_tag_becomes_canonical(self):
        from routes.tracks import _track_sidecar_path

        assert _track_sidecar_path("/m/ep.mkv", "ger", "srt") == "/m/ep.de.srt"
        assert _track_sidecar_path("/m/ep.mkv", "ENG", "ass") == "/m/ep.en.ass"

    def test_unknown_tag_passes_through(self):
        from routes.tracks import _track_sidecar_path

        assert _track_sidecar_path("/m/ep.mkv", "und", "srt") == "/m/ep.und.srt"

    @pytest.mark.parametrize("existing", ["ep.de.srt", "ep.ger.srt"])
    def test_existing_sidecar_is_found_under_either_name(self, tmp_path, existing):
        from routes.tracks import _existing_track_sidecar

        (tmp_path / existing).write_bytes(_SRT)
        found = _existing_track_sidecar(str(tmp_path / "ep.mkv"), "ger", "srt")
        assert found == str(tmp_path / existing)

    def test_nothing_on_disk(self, tmp_path):
        from routes.tracks import _existing_track_sidecar

        assert _existing_track_sidecar(str(tmp_path / "ep.mkv"), "ger", "srt") is None


class TestManualUpload:
    def test_alias_code_is_saved_under_canonical_name(self, tmp_path):
        video = tmp_path / "M.mkv"
        video.write_bytes(b"v")
        saved = save_manual_subtitle(str(video), _SRT, "srt", "ger", None, False, [str(tmp_path)])
        assert os.path.basename(saved) == "M.de.srt"

    def test_alias_code_conflicts_with_existing_canonical_sidecar(self, tmp_path):
        video = tmp_path / "M.mkv"
        video.write_bytes(b"v")
        save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, [str(tmp_path)])
        with pytest.raises(UploadError) as exc:
            save_manual_subtitle(str(video), _SRT, "srt", "ger", None, False, [str(tmp_path)])
        assert exc.value.status == 409
        assert not (tmp_path / "M.ger.srt").exists()


class TestAliasLookupCoversEveryCode:
    """Cold review (Codex, 2026-09-17): for a 'ger' track only .de and .ger were
    checked, so an existing .deu.srt led to a third copy of the same track."""

    @pytest.mark.parametrize(("tag", "existing"), [("ger", "deu"), ("deu", "ger"), ("eng", "en")])
    def test_any_alias_on_disk_is_found(self, tmp_path, tag, existing):
        from routes.tracks import _existing_track_sidecar

        (tmp_path / f"ep.{existing}.srt").write_bytes(_SRT)
        found = _existing_track_sidecar(str(tmp_path / "ep.mkv"), tag, "srt")
        assert found == str(tmp_path / f"ep.{existing}.srt")

    def test_a_different_language_is_not_mistaken_for_it(self, tmp_path):
        from routes.tracks import _existing_track_sidecar

        (tmp_path / "ep.fre.srt").write_bytes(_SRT)
        assert _existing_track_sidecar(str(tmp_path / "ep.mkv"), "ger", "srt") is None
