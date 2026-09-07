"""The translation source is chosen from the configured candidate languages,
never from "whatever else happens to be on disk or in the container".

Prod 2026-09-05: with no English sidecar present, ``find_any_source_sub``
fell back to ``sorted(found)[0]`` — alphabetically Arabic, then Vietnamese —
and 24 episodes were translated vi → de. The container path did the same:
``select_best_subtitle_stream`` P6 returned the first SRT that was not
German, which on a Blu-ray remux is the Arabic track.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _touch(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("x")


def _settings(**over):
    s = MagicMock()
    s.target_language = "de"
    s.source_language = "en"
    s.auto_translate_source_languages = ["en", "ja", "zh"]
    s.get_source_lang_tags = MagicMock(return_value={"en", "eng"})
    s.get_target_lang_tags = MagicMock(return_value={"de", "ger", "deu"})
    for k, v in over.items():
        setattr(s, k, v)
    return s


class TestFindAnySourceSub:
    def test_a_sidecar_outside_the_candidate_list_is_never_used(self, tmp_path):
        from translator._helpers import find_any_source_sub

        base = str(tmp_path / "Ep")
        _touch(base + ".mkv")
        _touch(base + ".vi.srt")
        _touch(base + ".ar.srt")

        with patch("translator._helpers.get_settings", return_value=_settings()):
            path, lang = find_any_source_sub(base + ".mkv")

        assert (path, lang) == (None, None)

    def test_candidates_are_honoured_in_configured_order(self, tmp_path):
        from translator._helpers import find_any_source_sub

        base = str(tmp_path / "Ep")
        _touch(base + ".mkv")
        _touch(base + ".zh.srt")
        _touch(base + ".ja.srt")
        _touch(base + ".ar.srt")

        with patch("translator._helpers.get_settings", return_value=_settings()):
            _path, lang = find_any_source_sub(base + ".mkv")

        assert lang == "ja"

    def test_explicit_preferences_reorder_but_never_extend_the_list(self, tmp_path):
        from translator._helpers import find_any_source_sub

        base = str(tmp_path / "Ep")
        _touch(base + ".mkv")
        _touch(base + ".ja.srt")
        _touch(base + ".zh.srt")
        _touch(base + ".fr.srt")

        with patch("translator._helpers.get_settings", return_value=_settings()):
            _path, lang = find_any_source_sub(
                base + ".mkv", preferred_languages=["ko", "zh", "fr", "ja"]
            )

        assert lang == "zh", "zh is preferred over ja here; fr is not a candidate at all"

    def test_the_first_preference_is_the_callers_own_source_and_always_counts(self, tmp_path):
        """translator.core passes the profile's source language first; a
        profile may name a language the global candidate list does not."""
        from translator._helpers import find_any_source_sub

        base = str(tmp_path / "Ep")
        _touch(base + ".mkv")
        _touch(base + ".fr.srt")

        with patch("translator._helpers.get_settings", return_value=_settings()):
            _path, lang = find_any_source_sub(base + ".mkv", preferred_languages=["fr", "ja"])

        assert lang == "fr"


class TestSelectBestSubtitleStream:
    def _probe(self, *langs):
        return {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": i + 4,
                    "tags": {"language": lang, "title": lang},
                }
                for i, lang in enumerate(langs)
            ]
        }

    def test_first_foreign_srt_is_no_longer_a_source(self):
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._probe("ara", "chi", "fre", "ger", "vie"))

        assert chosen is not None
        assert chosen["language"] == "chi", "zh is a configured candidate, Arabic is not"

    def test_candidate_order_wins_over_container_order(self):
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._probe("ara", "chi", "jpn", "ger"))

        assert chosen["language"] == "jpn"
        assert chosen["sub_index"] == 2

    def test_only_foreign_tracks_yields_the_target_track_as_last_resort(self):
        """P7 stays: a German-dub container with only a German SRT is still
        worth handing to the caller, which decides what to do with it."""
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._probe("ara", "vie", "ger"))

        assert chosen["language"] == "ger"

    def test_only_foreign_tracks_and_no_target_yields_nothing(self):
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._probe("ara", "vie"))

        assert chosen is None

    def _ass_probe(self, *tracks):
        return {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": i + 4,
                    "tags": {"language": lang, "title": title},
                }
                for i, (lang, title) in enumerate(tracks)
            ]
        }

    def test_a_full_ass_track_in_a_foreign_language_is_not_a_source(self):
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(
                self._ass_probe(("ara", "Full"), ("jpn", "Dialogue"))
            )

        assert chosen["language"] == "jpn"

    def test_an_untagged_ass_track_is_still_eligible(self):
        """Fansub MKVs rarely tag their tracks; the tag cannot disqualify
        what it does not name."""
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._ass_probe(("", "Full")))

        assert chosen is not None and chosen["language"] == ""

    def test_the_last_resort_ass_fallback_skips_foreign_tracks(self):
        from ass_probe import select_best_subtitle_stream

        with patch("ass_probe.get_settings", return_value=_settings()):
            chosen = select_best_subtitle_stream(self._ass_probe(("ara", "Signs"), ("vie", "OP")))

        assert chosen is None
