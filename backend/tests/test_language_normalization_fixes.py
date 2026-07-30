"""Unit tests for language-code normalisation on destructive paths.

Audit follow-up to issue #159: several keep-language checks compared raw
container/filename tags (3-letter "ger"/"eng") against 2-letter keep lists
without canonicalisation, so target-language tracks and sidecars were
classified as foreign/disposable.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetLanguageTags:
    def test_three_letter_input_expands_like_two_letter(self):
        from config_language_data import _get_language_tags

        assert {"de", "deu", "ger"} <= _get_language_tags("ger")
        assert _get_language_tags("ger") == _get_language_tags("de")

    def test_script_variant_includes_base_language_tags(self):
        from config_language_data import _get_language_tags

        tags = _get_language_tags("zh-hans")
        assert {"zh-hans", "zh", "zho", "chi"} <= tags

    def test_unknown_code_returns_itself(self):
        from config_language_data import _get_language_tags

        assert _get_language_tags("zz") == {"zz"}


class TestLanguageTableGaps:
    def test_bokmal_and_nynorsk_normalize_to_norwegian(self):
        from config_language_data import normalize_language_code

        assert normalize_language_code("nob") == "no"
        assert normalize_language_code("nb") == "no"
        assert normalize_language_code("nno") == "no"

    def test_bazarr_brazilian_portuguese_normalizes_to_pt(self):
        from config_language_data import normalize_language_code

        assert normalize_language_code("pob") == "pt"
        assert normalize_language_code("pt-br") == "pt"


class TestComputeKeepLangs:
    def _settings(self, auto_translate=False, source_language=""):
        s = MagicMock()
        s.wanted_auto_translate = auto_translate
        s.source_language = source_language
        return s

    def test_script_variant_target_keeps_base_code(self):
        from services.embedded_extractor import compute_keep_langs

        keep = compute_keep_langs({"target_languages": ["zh-hans"]}, self._settings())
        assert "zh-hans" in keep
        assert "zh" in keep, "generic chi/zho/zh tags must never be trashed for zh-hans"

    def test_und_only_targets_produce_empty_keep_set(self):
        from services.embedded_extractor import compute_keep_langs

        keep = compute_keep_langs(
            {"target_languages": ["und", "und1", "und2"]}, self._settings()
        )
        assert keep == set(), "an und-only keep set must trigger the empty-set no-op guards"

    def test_source_language_added_when_auto_translate(self):
        from services.embedded_extractor import compute_keep_langs

        keep = compute_keep_langs(
            {"target_languages": ["de"]},
            self._settings(auto_translate=True, source_language="eng"),
        )
        assert keep == {"de", "en"}


class TestPickPrimary:
    def test_three_letter_track_matches_two_letter_target(self):
        from services.embedded_extractor import _pick_primary

        extracted = [
            {"language": "jpn", "format": "ass", "sub_index": 0, "output_path": "/a.jpn.ass"},
            {"language": "ger", "format": "srt", "sub_index": 1, "output_path": "/a.ger.srt"},
        ]
        path, fmt, lang = _pick_primary(extracted, "de")
        assert lang == "ger"
        assert path == "/a.ger.srt"

    def test_no_prefix_false_positive_estonian_for_spanish(self):
        from services.embedded_extractor import _pick_primary

        extracted = [
            {"language": "est", "format": "srt", "sub_index": 0, "output_path": "/a.est.srt"},
            {"language": "jpn", "format": "ass", "sub_index": 1, "output_path": "/a.jpn.ass"},
        ]
        path, fmt, lang = _pick_primary(extracted, "es")
        # No Spanish track exists — fall back to the first entry, but never
        # "match" Estonian just because it shares the prefix.
        assert lang == "est"  # fallback extracted[0], not a target match
        # The regression: with prefix matching, "est" was treated as a target
        # match for "es". Verify a real Spanish track wins when present.
        extracted.append(
            {"language": "spa", "format": "srt", "sub_index": 2, "output_path": "/a.spa.srt"}
        )
        path, fmt, lang = _pick_primary(extracted, "es")
        assert lang == "spa"


class TestRemoveForeignSubtitleStreamsDefense:
    def test_bare_two_letter_target_spares_three_letter_tagged_stream(self, tmp_path):
        """Even when a caller (wrongly) passes bare 2-letter codes, the
        target-language stream must survive."""
        import remux as remux_mod

        video = tmp_path / "ep.mkv"
        video.write_bytes(b"fake")

        probe = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "index": 2,
                    "tags": {"language": "ger"},
                },
                {
                    "codec_type": "subtitle",
                    "index": 3,
                    "tags": {"language": "jpn"},
                },
            ]
        }

        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams", return_value="/bak") as mock_remove,
        ):
            remux_mod.remove_foreign_subtitle_streams(
                video_path=str(video),
                target_languages={"de"},
            )

        streams = mock_remove.call_args.kwargs["streams"]
        assert streams == [(3, 1)], "ger must not be foreign for target {'de'}"


class TestResolveCombineSources:
    def test_three_letter_sidecar_tags_match_profile_codes(self, tmp_path):
        from services.combine_service import resolve_combine_sources

        sidecars = [
            {"language": "ger", "format": "ass", "path": str(tmp_path / "ep.ger.ass")},
            {"language": "eng", "format": "ass", "path": str(tmp_path / "ep.eng.ass")},
        ]

        with patch(
            "services.sidecar_scan.scan_subtitle_sidecars", return_value=sidecars
        ):
            present, missing = resolve_combine_sources(str(tmp_path / "ep.mkv"), ["de", "en"])

        assert missing == []
        assert [p["language"] for p in present] == ["de", "en"]
        assert present[0]["path"].endswith("ep.ger.ass")
