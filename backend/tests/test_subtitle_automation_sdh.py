"""SDH-tolerance tests (Phase 5).

Covers:
- `is_sdh_stream()` helper: recognizes 'SDH', 'CC', 'HI', 'hearing_impaired'
  markers in either the title or disposition flags.
- `_collect_subtitle_streams`: respects `embedded_allow_sdh`. When False,
  SDH streams are filtered out entirely. When True (default), they are
  collected normally.
- `embedded.py` provider: applies `embedded_sdh_penalty` to score_bonus so
  a non-SDH track wins when both are present.
"""

from unittest.mock import patch

import pytest

from ass_probe import is_sdh_stream
from config_settings import Settings
from routes.wanted.batch_probe import _collect_subtitle_streams


class TestIsSdhStream:
    def test_title_with_sdh_suffix(self):
        stream = {"codec_type": "subtitle", "tags": {"title": "English (SDH)"}}
        assert is_sdh_stream(stream) is True

    def test_title_with_cc(self):
        stream = {"codec_type": "subtitle", "tags": {"title": "English CC"}}
        assert is_sdh_stream(stream) is True

    def test_title_with_hi(self):
        stream = {"codec_type": "subtitle", "tags": {"title": "English [HI]"}}
        assert is_sdh_stream(stream) is True

    def test_title_hearing_impaired_flag_true(self):
        stream = {
            "codec_type": "subtitle",
            "tags": {"title": "English"},
            "disposition": {"hearing_impaired": 1},
        }
        assert is_sdh_stream(stream) is True

    def test_normal_title_is_false(self):
        stream = {"codec_type": "subtitle", "tags": {"title": "English"}}
        assert is_sdh_stream(stream) is False

    def test_missing_tags_is_false(self):
        stream = {"codec_type": "subtitle"}
        assert is_sdh_stream(stream) is False

    def test_sdh_substring_in_language_code_does_not_match(self):
        """Only the title/disposition signal SDH. Language codes (which could
        contain the substring accidentally) must not trigger it."""
        stream = {
            "codec_type": "subtitle",
            "tags": {"title": "", "language": "sdh-fake"},
        }
        assert is_sdh_stream(stream) is False


class TestCollectSubtitleStreamsRespectsToggle:
    def _probe_with_eng_sdh_and_eng_plain(self):
        return {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 3,
                    "tags": {"language": "eng", "title": "English"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 4,
                    "tags": {"language": "eng", "title": "English (SDH)"},
                },
            ]
        }

    def test_keeps_both_when_allow_sdh_true(self):
        probe = self._probe_with_eng_sdh_and_eng_plain()
        fake = Settings(embedded_allow_sdh=True)
        with patch("routes.wanted.batch_probe.get_settings", return_value=fake):
            streams = _collect_subtitle_streams(probe)
        assert len(streams) == 2

    def test_drops_sdh_when_allow_sdh_false(self):
        probe = self._probe_with_eng_sdh_and_eng_plain()
        fake = Settings(embedded_allow_sdh=False)
        with patch("routes.wanted.batch_probe.get_settings", return_value=fake):
            streams = _collect_subtitle_streams(probe)
        assert len(streams) == 1
        # The one kept is the plain English track.
        assert streams[0]["stream_index"] == 3

    def test_keeps_sdh_when_only_source(self):
        """If SDH is the ONLY English track (Marvel Disney pattern) and
        allow_sdh=True, SDH must pass through as the extracted source."""
        probe = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 4,
                    "tags": {"language": "eng", "title": "English (SDH)"},
                }
            ]
        }
        fake = Settings(embedded_allow_sdh=True)
        with patch("routes.wanted.batch_probe.get_settings", return_value=fake):
            streams = _collect_subtitle_streams(probe)
        assert len(streams) == 1


class TestEmbeddedProviderScoring:
    """The embedded provider must apply the configured SDH penalty so that
    a non-SDH track wins a score tie with an otherwise-equal SDH track."""

    @pytest.fixture
    def base_probe(self):
        return {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 3,
                    "tags": {"language": "eng", "title": "English"},
                    "disposition": {},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 4,
                    "tags": {"language": "eng", "title": "English (SDH)"},
                    "disposition": {},
                },
            ]
        }

    def test_sdh_gets_configured_penalty(self, base_probe, tmp_path, monkeypatch):
        """score_bonus on the SDH result should be smaller than the non-SDH
        one by exactly `embedded_sdh_penalty`."""
        from providers.embedded import EmbeddedSubtitlesProvider, VideoQuery

        media = tmp_path / "x.mkv"
        media.write_bytes(b"fake")  # only existence matters
        monkeypatch.setattr(
            "providers.embedded.get_media_streams", lambda *a, **kw: base_probe
        )
        fake = Settings(embedded_allow_sdh=True, embedded_sdh_penalty=7)
        with patch("providers.embedded.get_settings", return_value=fake):
            results = EmbeddedSubtitlesProvider().search(
                VideoQuery(
                    file_path=str(media),
                    languages=["en"],
                    title="Test Movie",
                )
            )
        assert len(results) == 2
        # Locate plain vs SDH by title.
        plain = next(r for r in results if "SDH" not in r.release_info)
        sdh = next(r for r in results if "SDH" in r.release_info)
        plain_bonus = plain.provider_data["score_bonus"]
        sdh_bonus = sdh.provider_data["score_bonus"]
        assert sdh_bonus == plain_bonus - 7

    def test_sdh_blocked_when_allow_sdh_off(self, base_probe, tmp_path, monkeypatch):
        """With allow_sdh=False the provider must not even return SDH tracks."""
        from providers.embedded import EmbeddedSubtitlesProvider, VideoQuery

        media = tmp_path / "x.mkv"
        media.write_bytes(b"fake")
        monkeypatch.setattr(
            "providers.embedded.get_media_streams", lambda *a, **kw: base_probe
        )
        fake = Settings(embedded_allow_sdh=False, embedded_sdh_penalty=5)
        with patch("providers.embedded.get_settings", return_value=fake):
            results = EmbeddedSubtitlesProvider().search(
                VideoQuery(
                    file_path=str(media),
                    languages=["en"],
                    title="Test Movie",
                )
            )
        # Only the non-SDH track remains.
        assert len(results) == 1
        assert "SDH" not in results[0].release_info
