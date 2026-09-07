"""The extractor only extracts the languages the profile keeps — and never
adopts a sidecar whose content contradicts its name.

Prod 2026-09-07, one Blu-ray remux with 19 subtitle tracks: every text track
was extracted (13 full reads of a 7.7 GB file), the twelve foreign sidecars
were trashed by the nightly cleanup, and the next day's run extracted them
all over again — 4 152 extract passes in one day, 3 136 sidecars trashed.
In between, the search found the Vietnamese sidecar and translated it into
German. Meanwhile the ``.de.srt`` next to that remux held the ARABIC track
(written by a spring-2026 extractor) and the canonical-name fallback happily
reported it as the German output on every pass.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

ARABIC = (
    "1\n00:00:27,527 --> 00:00:30,655\n‫كانت هناك حرب كبيرة ذات يوم.\n\n"
    "2\n00:00:31,489 --> 00:00:37,245\n‫واصل المحاربون الشهيرون القتال، مع قناعاتهم\n\n"
    "3\n00:00:37,829 --> 00:00:40,331\n‫لكن الصراع لم يشهد أي منتصر.\n\n"
)
GERMAN = (
    "1\n00:00:27,527 --> 00:00:31,031\nEinst gab es einen großen Krieg.\n\n"
    "2\n00:00:31,573 --> 00:00:37,704\nBerühmte Krieger kämpften mit ihren Überzeugungen\n\n"
)


def _probe(*streams):
    return {"streams": list(streams)}


def _sub_stream(index: int, lang: str, codec: str = "subrip"):
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


def _canonical_path(tmp_path):
    from config_language_data import normalize_language_code

    def _f(file_path, stream_info):
        lang = normalize_language_code(stream_info["language"])
        return str(tmp_path / f"Ep.{lang}.{stream_info['format']}")

    return _f


def _legacy_path(tmp_path):
    def _f(file_path, stream_info):
        return str(tmp_path / f"Ep.{stream_info['language']}.{stream_info['format']}")

    return _f


def _fake_extract(content_by_sub_index: dict[int, str]):
    def _f(file_path, stream_info, output_path):
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(content_by_sub_index.get(stream_info["sub_index"], "x"))

    return _f


@pytest.fixture
def pipeline(tmp_path):
    """Run extract_and_cleanup against a fake container with real files on disk."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")

    def _run(streams, *, keep_langs, target_language="de", content=None, trash_ok=True, **kwargs):
        trash = _fake_trash(tmp_path) if trash_ok else (lambda _path: False)
        with (
            patch("config.get_settings", return_value=_settings_mock()),
            patch("ass_probe.is_sdh_stream", return_value=False),
            patch(
                "ass_utils.get_subtitle_stream_output_path", side_effect=_canonical_path(tmp_path)
            ),
            patch(
                "ass_utils.get_legacy_subtitle_stream_output_path",
                side_effect=_legacy_path(tmp_path),
            ),
            patch(
                "ass_utils.extract_subtitle_stream", side_effect=_fake_extract(content or {})
            ) as ex,
            patch("services.embedded_extractor.remove_streams_from_container") as rm,
            patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
            patch("services.embedded_extractor.purge_signs_after_extract", return_value=0),
            patch("services.embedded_extractor._trash_path", side_effect=trash) as tr,
        ):
            result = embedded_extractor.extract_and_cleanup(
                str(video),
                _probe(*streams),
                keep_langs=keep_langs,
                target_language=target_language,
                **kwargs,
            )
        return result, ex, rm, tr

    return _run


def _fake_trash(tmp_path):
    def _f(path):
        import os

        trash = tmp_path / "_trash"
        trash.mkdir(exist_ok=True)
        os.replace(path, trash / os.path.basename(path))
        return True

    return _f


REMUX = [
    _sub_stream(4, "eng", "hdmv_pgs_subtitle"),
    _sub_stream(7, "ara"),
    _sub_stream(8, "chi"),
    _sub_stream(10, "fre"),
    _sub_stream(11, "ger"),
    _sub_stream(12, "ind"),
    _sub_stream(14, "jpn"),
    _sub_stream(22, "vie"),
]


class TestOnlyKeptLanguagesAreExtracted:
    def test_foreign_tracks_are_never_extracted(self, pipeline):
        result, ex, _rm, _tr = pipeline(REMUX, keep_langs={"de", "en"})

        extracted_langs = sorted(c.args[1]["language"] for c in ex.call_args_list)
        assert extracted_langs == ["ger"], "only the German track may cost a container read"
        assert [e["language"] for e in result.extracted] == ["ger"]
        assert result.primary_language == "ger"

    def test_unknown_and_und_tags_are_still_extracted(self, pipeline):
        """A track we cannot classify might be the one the user wants."""
        streams = [_sub_stream(3, "und"), _sub_stream(4, "enm"), _sub_stream(5, "fre")]
        _result, ex, _rm, _tr = pipeline(streams, keep_langs={"de"})

        assert sorted(c.args[1]["language"] for c in ex.call_args_list) == ["enm", "und"]

    def test_empty_keep_set_extracts_everything(self, pipeline):
        """No profile languages → no opinion → the old behaviour."""
        _result, ex, _rm, _tr = pipeline(REMUX, keep_langs=set())

        assert len(ex.call_args_list) == 7

    def test_nothing_wanted_in_the_container_reports_nothing_extracted(self, pipeline):
        streams = [_sub_stream(7, "ara"), _sub_stream(22, "vie")]
        result, ex, _rm, _tr = pipeline(streams, keep_langs={"de", "en"})

        ex.assert_not_called()
        assert result.any_extracted is False
        assert result.primary_output_path is None

    def test_opt_in_container_removal_still_strips_the_skipped_foreign_tracks(self, pipeline):
        """The opt-in used to strip foreign tracks by extracting them first.
        Skipping the extraction must not silently disable the strip."""
        _result, _ex, rm, _tr = pipeline(REMUX, keep_langs={"de", "en"}, remove_from_container=True)

        assert sorted(rm.call_args.args[1]) == [(7, 1), (8, 2), (10, 3), (12, 5), (14, 6), (22, 7)]

    def test_opt_in_removal_never_touches_kept_or_unknown_tracks(self, pipeline):
        streams = [_sub_stream(3, "und"), _sub_stream(7, "ara"), _sub_stream(11, "ger")]
        _result, _ex, rm, _tr = pipeline(streams, keep_langs={"de"}, remove_from_container=True)

        assert rm.call_args.args[1] == [(7, 1)]


class TestExistingSidecarsAreNotAdoptedBlindly:
    def test_a_de_sidecar_holding_arabic_is_trashed_and_the_legacy_german_adopted(
        self, pipeline, tmp_path
    ):
        (tmp_path / "Ep.de.srt").write_text(ARABIC, encoding="utf-8")
        (tmp_path / "Ep.ger.srt").write_text(GERMAN, encoding="utf-8")

        result, ex, _rm, tr = pipeline([_sub_stream(11, "ger")], keep_langs={"de"})

        assert tr.call_count == 1
        assert not (tmp_path / "Ep.de.srt").exists()
        assert (tmp_path / "_trash" / "Ep.de.srt").exists()
        ex.assert_not_called()
        assert result.primary_output_path == str(tmp_path / "Ep.ger.srt")

    def test_a_de_sidecar_holding_arabic_is_replaced_by_a_fresh_extract(self, pipeline, tmp_path):
        (tmp_path / "Ep.de.srt").write_text(ARABIC, encoding="utf-8")

        result, ex, _rm, _tr = pipeline(
            [_sub_stream(11, "ger")], keep_langs={"de"}, content={0: GERMAN}
        )

        assert ex.call_count == 1
        assert result.primary_output_path == str(tmp_path / "Ep.de.srt")
        assert "Krieg" in (tmp_path / "Ep.de.srt").read_text(encoding="utf-8")

    def test_a_legacy_sidecar_holding_the_wrong_script_is_not_adopted_either(
        self, pipeline, tmp_path
    ):
        (tmp_path / "Ep.ger.srt").write_text(ARABIC, encoding="utf-8")

        result, ex, _rm, tr = pipeline(
            [_sub_stream(11, "ger")], keep_langs={"de"}, content={0: GERMAN}
        )

        assert tr.call_count == 1
        assert ex.call_count == 1
        assert result.primary_output_path == str(tmp_path / "Ep.de.srt")

    def test_a_genuine_german_sidecar_is_adopted_without_a_container_read(self, pipeline, tmp_path):
        (tmp_path / "Ep.de.srt").write_text(GERMAN, encoding="utf-8")

        result, ex, _rm, tr = pipeline([_sub_stream(11, "ger")], keep_langs={"de"})

        ex.assert_not_called()
        tr.assert_not_called()
        assert result.primary_output_path == str(tmp_path / "Ep.de.srt")

    def test_a_rejected_sidecar_is_overwritten_when_the_trash_move_fails(self, pipeline, tmp_path):
        """Codex review 2026-09-07: a failed quarantine used to leave the wrong
        file in place, and the next check adopted it after all."""
        (tmp_path / "Ep.de.srt").write_text(ARABIC, encoding="utf-8")
        (tmp_path / "Ep.ger.srt").write_text(GERMAN, encoding="utf-8")

        result, ex, _rm, _tr = pipeline(
            [_sub_stream(11, "ger")], keep_langs={"de"}, content={0: GERMAN}, trash_ok=False
        )

        assert result.primary_output_path == str(tmp_path / "Ep.ger.srt")
        ex.assert_not_called()
        # the Arabic file is still there (move failed) but was not adopted
        assert "Krieg" not in (tmp_path / "Ep.de.srt").read_text(encoding="utf-8")

    def test_an_unreadable_sidecar_is_adopted_as_before(self, pipeline, tmp_path):
        """A file we cannot read is not evidence of anything; keep the old behaviour."""
        (tmp_path / "Ep.de.srt").write_bytes(b"\xff\xfe\x00\x00")

        result, ex, _rm, tr = pipeline([_sub_stream(11, "ger")], keep_langs={"de"})

        ex.assert_not_called()
        tr.assert_not_called()
        assert result.primary_output_path == str(tmp_path / "Ep.de.srt")


class TestBracketedPathsAreCleanedUpToo:
    """``glob.glob`` reads ``[Oshi no Ko]`` as a character class. Every sidecar
    under a bracketed directory or file name escaped the extract-time trash
    (prod: ``sidecars_trashed: 0`` on all 13 episodes, every day)."""

    def test_trash_non_target_sidecars_handles_brackets_in_the_directory(self, tmp_path):
        from remux import trash_non_target_sidecars

        d = tmp_path / "[Oshi no Ko] - [MeinStar] (2023)"
        d.mkdir()
        video = d / "Ep - S02E01 Remux.mkv"
        video.write_bytes(b"")
        (d / "Ep - S02E01 Remux.ar.srt").write_text("x")
        (d / "Ep - S02E01 Remux.de.srt").write_text("x")

        moved = trash_non_target_sidecars(
            video_path=str(video), keep_langs={"de"}, trash_dir=str(tmp_path / "_trash")
        )

        assert [p.split("Remux.")[-1] for p, _ in moved] == ["ar.srt"]
        assert (d / "Ep - S02E01 Remux.de.srt").exists()

    def test_trash_non_target_sidecars_handles_brackets_in_the_file_name(self, tmp_path):
        from remux import trash_non_target_sidecars

        video = tmp_path / "Movie (2026) [WEBDL-1080p] [imdb-tt38872297].mkv"
        video.write_bytes(b"")
        (tmp_path / "Movie (2026) [WEBDL-1080p] [imdb-tt38872297].ja.srt").write_text("x")

        moved = trash_non_target_sidecars(
            video_path=str(video), keep_langs={"de"}, trash_dir=str(tmp_path / "_trash")
        )

        assert len(moved) == 1

    def test_signs_purge_sees_sidecars_under_bracketed_names(self, tmp_path):
        from services import embedded_extractor

        d = tmp_path / "[Group] Show"
        d.mkdir()
        video = d / "Ep.mkv"
        video.write_bytes(b"")
        signs = d / "Ep.en.signs.ass"
        signs.write_text("x")
        full = d / "Ep.en.ass"
        full.write_text("x")

        with (
            patch(
                "config.get_settings",
                return_value=_settings_mock(cleanup_signs_removal_level="signs_forced"),
            ),
            patch("services.subtitle_signs.classify_sidecar", return_value="signs"),
            patch("services.subtitle_signs.is_removable", return_value=True),
            patch("services.embedded_extractor._trash_path", return_value=True) as tr,
        ):
            trashed = embedded_extractor.purge_signs_after_extract(
                str(video), extracted_paths=[str(signs)]
            )

        assert trashed == 1
        assert tr.call_args.args[0] == str(signs)
