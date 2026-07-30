"""Container-removal gating tests for the shared extract pipeline (issue #159).

The container rewrite after extraction used to be unconditional: every
extracted stream — including target-language ones, duplicates that were
never extracted, and streams whose sidecar already existed from an earlier
run — was remuxed out of the MKV. These tests pin the fixed contract:

  - removal is opt-in (``remove_from_container``, default False)
  - streams in ``keep_langs`` are never removed
  - empty ``keep_langs`` removes nothing (never strip blind)
  - only freshly extracted streams are removal candidates
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _probe(*streams):
    return {"streams": list(streams)}


def _sub_stream(index: int, lang: str, codec: str = "ass"):
    return {
        "codec_type": "subtitle",
        "codec_name": codec,
        "index": index,
        "tags": {"language": lang},
    }


def _settings_mock(**overrides):
    s = MagicMock()
    s.embedded_allow_sdh = True
    s.remux_use_reflink = False
    s.remux_trash_dir = ".sublarr"
    s.cleanup_signs_removal_level = "off"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _out_path_for(tmp_path):
    """get_subtitle_stream_output_path replacement: unique path per stream."""

    def _f(file_path, stream_info):
        return str(tmp_path / f"Ep.{stream_info['language']}.{stream_info['sub_index']}.ass")

    return _f


class TestExtractAndCleanupContainerRemoval:
    def test_default_never_removes_streams(self, tmp_path):
        """Without the opt-in, extraction must not touch the container."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_out_path_for(tmp_path)),
            patch("ass_utils.extract_subtitle_stream"),
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        ):
            result = embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "eng"), _sub_stream(3, "jpn")),
                keep_langs={"en"},
            )

        assert result.any_extracted is True
        mock_remove.assert_not_called()

    def test_opt_in_removal_spares_keep_langs_streams(self, tmp_path):
        """With the opt-in ON, a stream whose 3-letter tag normalises into
        keep_langs (eng → en) must survive; only disposable languages go."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_out_path_for(tmp_path)),
            patch("ass_utils.extract_subtitle_stream"),
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        ):
            embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "eng"), _sub_stream(3, "jpn")),
                keep_langs={"en"},
                remove_from_container=True,
            )

        mock_remove.assert_called_once()
        removed = mock_remove.call_args.args[1]
        assert removed == [(3, 1)], "only the jpn stream may be removed, eng is kept"

    def test_opt_in_with_empty_keep_langs_removes_nothing(self, tmp_path):
        """Empty keep set → no removal at all (mirror of the
        remove_foreign_subtitle_streams empty-target-set guard)."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_out_path_for(tmp_path)),
            patch("ass_utils.extract_subtitle_stream"),
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
        ):
            embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "eng"), _sub_stream(3, "jpn")),
                keep_langs=set(),
                remove_from_container=True,
            )

        removed = mock_remove.call_args.args[1]
        assert removed == []

    def test_unknown_language_tag_is_never_removed(self, tmp_path):
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_out_path_for(tmp_path)),
            patch("ass_utils.extract_subtitle_stream"),
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        ):
            embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "und"), _sub_stream(3, "jpn")),
                keep_langs={"de"},
                remove_from_container=True,
            )

        removed = mock_remove.call_args.args[1]
        assert removed == [(3, 1)], "und stream must be kept"

    def test_preexisting_sidecar_not_requeued_for_removal(self, tmp_path):
        """A stream whose sidecar already exists was NOT extracted in this
        pass — repeat runs must not remux the container again."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")
        existing = tmp_path / "Ep.jpn.0.ass"
        existing.write_text("dialogue", encoding="utf-8")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_out_path_for(tmp_path)),
            patch("ass_utils.extract_subtitle_stream") as mock_extract,
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        ):
            result = embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "jpn")),
                keep_langs={"de"},
                remove_from_container=True,
            )

        mock_extract.assert_not_called()
        assert result.any_extracted is True
        removed = mock_remove.call_args.args[1]
        assert removed == []

    def test_duplicate_lang_fmt_stream_not_removed_without_extraction(self, tmp_path):
        """Two eng+ass tracks (anime 'Full' + 'Signs') collapse to one output
        path. The second track is never extracted — it must therefore never
        be removed from the container (its content exists nowhere else)."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        def _same_path(file_path, stream_info):
            return str(tmp_path / f"Ep.{stream_info['language']}.ass")

        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch("ass_utils.get_subtitle_stream_output_path", side_effect=_same_path),
            patch("ass_utils.extract_subtitle_stream"),
            patch("services.embedded_extractor.remove_streams_from_container") as mock_remove,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        ):
            result = embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(_sub_stream(2, "eng"), _sub_stream(3, "eng")),
                keep_langs={"de"},
                remove_from_container=True,
            )

        assert len(result.extracted) == 1
        removed = mock_remove.call_args.args[1]
        assert removed == [(2, 0)], "the never-extracted duplicate must stay in the container"


class TestFilterStreamsSafeToRemove:
    def test_empty_candidates(self):
        from services.embedded_extractor import filter_streams_safe_to_remove

        assert filter_streams_safe_to_remove([], [], {"en"}) == []

    def test_three_letter_tag_matches_two_letter_keep(self):
        from services.embedded_extractor import filter_streams_safe_to_remove

        streams = [
            {"stream_index": 2, "language": "eng"},
            {"stream_index": 3, "language": "ger"},
            {"stream_index": 4, "language": "jpn"},
        ]
        candidates = [(2, 0), (3, 1), (4, 2)]

        safe = filter_streams_safe_to_remove(streams, candidates, {"en", "de"})

        assert safe == [(4, 2)]

    def test_empty_keep_langs_never_strips(self):
        from services.embedded_extractor import filter_streams_safe_to_remove

        streams = [{"stream_index": 2, "language": "jpn"}]
        assert filter_streams_safe_to_remove(streams, [(2, 0)], set()) == []


class TestExtractEmbeddedSubResolvesSetting:
    @pytest.mark.parametrize("setting_value", [False, True])
    def test_setting_passthrough(self, tmp_path, setting_value):
        from services import embedded_extractor
        from services.embedded_extractor import ExtractResult

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")

        settings = _settings_mock(
            embedded_extract_remove_from_container=setting_value,
            enable_subtitle_repair=False,
            target_language="de",
            media_path=str(tmp_path),
        )

        item = {"id": 1, "target_language": "de"}
        fake_result = ExtractResult(
            any_extracted=True,
            extracted=[{"language": "de", "format": "srt", "sub_index": 0, "output_path": "x"}],
            primary_output_path=str(video),
            primary_format="srt",
            primary_language="de",
            sidecars_trashed=0,
        )

        with (
            patch("config.get_settings", return_value=settings),
            patch("db.wanted.get_wanted_item", return_value=item),
            patch("db.wanted.update_existing_sub"),
            patch("db.wanted.update_wanted_status"),
            patch("ass_utils.get_media_streams", return_value={"streams": []}),
            patch("services.embedded_extractor.resolve_profile_for_item", return_value={"target_languages": ["de"]}),
            patch("services.embedded_extractor.extract_and_cleanup", return_value=fake_result) as mock_eac,
            patch("services.embedded_extractor.emit_event"),
            patch("services.embedded_extractor.log_activity"),
        ):
            embedded_extractor.extract_embedded_sub(1, str(video))

        assert mock_eac.call_args.kwargs["remove_from_container"] is setting_value
