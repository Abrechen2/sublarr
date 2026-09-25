"""SubDL provider: response parsing, downloads, pack episode picking (#212).

The fixtures mirror the key set captured from the live API in #212:
``subtitles[]`` carry author, episode, episode_end, episode_from, fps,
framerate, full_season, hi, lang, language, name, release_name, season,
subtitlePage and url; ``sd_id``/``year`` live only on ``results[]`` (the show).
"""

from __future__ import annotations

import io
import logging
import zipfile
from unittest.mock import MagicMock, patch

import pytest
import requests

from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotApplicableError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleResult,
    VideoQuery,
)
from providers.subdl import SubDLProvider, _pick_best_subtitle

API_KEY = "SECRETKEY1234567890"
_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def _subtitle(**overrides) -> dict:
    sub = {
        "author": "someone",
        "episode": None,
        "episode_end": 0,
        "episode_from": 0,
        "fps": None,
        "framerate": 0,
        "full_season": False,
        "hi": False,
        "lang": "English",
        "language": "EN",
        "name": "SUBDL.com::Ratatouille.2007.1080p.BluRay.x264-GROUP.zip",
        "release_name": "Ratatouille.2007.1080p.BluRay.x264-GROUP",
        "season": 0,
        "subtitlePage": "/subtitle/sd12345/ratatouille",
        "url": f"/subtitle/3389884-8312959.zip?api_key={API_KEY}",
    }
    sub.update(overrides)
    return sub


def _response(subtitles: list[dict], year: int = 2007, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "{}"
    resp.json.return_value = {
        "status": True,
        "results": [
            {
                "sd_id": 12345,
                "type": "movie",
                "name": "Ratatouille",
                "imdb_id": "tt0382932",
                "tmdb_id": 2062,
                "first_air_date": None,
                "year": year,
            }
        ],
        "subtitles": subtitles,
    }
    return resp


def _provider(resp: MagicMock | None = None) -> SubDLProvider:
    provider = SubDLProvider(api_key=API_KEY)
    provider.session = MagicMock()
    if resp is not None:
        provider.session.get.return_value = resp
    return provider


def _movie_query(**kw) -> VideoQuery:
    base = {"title": "Ratatouille", "year": 2007, "imdb_id": "tt0382932", "languages": ["en"]}
    base.update(kw)
    return VideoQuery(**base)


def _episode_query(**kw) -> VideoQuery:
    base = {
        "series_title": "City Hunter",
        "season": 1,
        "episode": 3,
        "imdb_id": "tt0200351",
        "languages": ["en"],
    }
    base.update(kw)
    return VideoQuery(**base)


# ---------------------------------------------------------------------------
# search(): field mapping
# ---------------------------------------------------------------------------


class TestSearchFieldMapping:
    def test_language_is_iso_code_not_display_name(self):
        results = _provider(_response([_subtitle()])).search(_movie_query())
        assert [r.language for r in results] == ["en"]

    def test_lowercase_display_name_never_leaks_into_language(self):
        sub = _subtitle(lang="english", language="EN")
        results = _provider(_response([sub])).search(_movie_query())
        assert results[0].language == "en"

    def test_brazilian_portuguese_code_maps_to_pt(self):
        sub = _subtitle(lang="Brazillian Portuguese", language="BR_PT")
        results = _provider(_response([sub])).search(_movie_query(languages=["pt"]))
        assert results[0].language == "pt"

    def test_subtitle_id_and_download_url_come_from_url(self):
        result = _provider(_response([_subtitle()])).search(_movie_query())[0]
        assert result.subtitle_id == "3389884-8312959"
        assert result.download_url == "https://dl.subdl.com/subtitle/3389884-8312959.zip"

    def test_api_key_is_stripped_from_everything_stored(self):
        result = _provider(_response([_subtitle()])).search(_movie_query())[0]
        assert API_KEY not in repr(result)
        assert API_KEY not in repr(result.provider_data)

    def test_hi_flag_maps_to_hearing_impaired(self):
        results = _provider(_response([_subtitle(hi=True), _subtitle(hi=False)])).search(
            _movie_query()
        )
        assert [r.hearing_impaired for r in results] == [True, False]

    def test_year_is_read_from_the_show(self):
        result = _provider(_response([_subtitle()], year=2007)).search(_movie_query())[0]
        assert "year" in result.matches

    def test_year_mismatch_on_the_show_is_no_match(self):
        result = _provider(_response([_subtitle()], year=2011)).search(_movie_query())[0]
        assert "year" not in result.matches

    def test_title_search_sends_year(self):
        provider = _provider(_response([_subtitle()]))
        provider.search(_movie_query(imdb_id=""))
        params = provider.session.get.call_args.kwargs["params"]
        assert params["film_name"] == "Ratatouille"
        assert params["year"] == 2007

    def test_subtitle_without_url_is_skipped(self):
        results = _provider(_response([_subtitle(url="")])).search(_movie_query())
        assert results == []


# ---------------------------------------------------------------------------
# search(): episode coverage
# ---------------------------------------------------------------------------


class TestSearchEpisodeCoverage:
    def test_pack_that_does_not_cover_the_episode_is_skipped(self):
        sub = _subtitle(season=1, full_season=True, episode_from=1, episode_end=12)
        results = _provider(_response([sub])).search(_episode_query(episode=13))
        assert results == []

    def test_pack_that_covers_the_episode_is_kept(self):
        sub = _subtitle(season=1, full_season=True, episode_from=1, episode_end=12)
        results = _provider(_response([sub])).search(_episode_query(episode=5))
        assert len(results) == 1

    def test_pack_covering_the_absolute_episode_is_kept(self):
        sub = _subtitle(season=4, full_season=True, episode_from=50, episode_end=70)
        query = _episode_query(season=4, episode=19, absolute_episode=64)
        assert len(_provider(_response([sub])).search(query)) == 1

    def test_single_episode_for_another_episode_is_skipped(self):
        sub = _subtitle(season=1, episode=7)
        assert _provider(_response([sub])).search(_episode_query(episode=3)) == []

    def test_matching_single_episode_gets_episode_match(self):
        sub = _subtitle(season=1, episode=3)
        result = _provider(_response([sub])).search(_episode_query(episode=3))[0]
        assert {"season", "episode"} <= result.matches

    def test_absolute_episode_is_carried_to_download(self):
        sub = _subtitle(season=4, full_season=True)
        query = _episode_query(season=4, episode=19, absolute_episode=64)
        result = _provider(_response([sub])).search(query)[0]
        assert result.provider_data["query_absolute_episode"] == 64


# ---------------------------------------------------------------------------
# search(): failures are failures, and never leak the key
# ---------------------------------------------------------------------------


def _conn_error() -> requests.ConnectionError:
    return requests.ConnectionError(
        "HTTPSConnectionPool(host='api.subdl.com', port=443): Max retries exceeded with "
        f"url: /api/v1/subtitles?api_key={API_KEY}&subs_per_page=30 "
        "(Caused by NameResolutionError: Failed to resolve 'api.subdl.com')"
    )


class TestSearchFailures:
    def test_server_error_raises_instead_of_empty(self):
        with pytest.raises(ProviderError):
            _provider(_response([], status_code=500)).search(_movie_query())

    def test_connection_error_raises_provider_error_without_key(self, caplog):
        provider = _provider()
        provider.session.get.side_effect = _conn_error()
        caplog.set_level(logging.DEBUG)
        with pytest.raises(ProviderError) as excinfo:
            provider.search(_movie_query())
        assert API_KEY not in str(excinfo.value)
        assert "max retries exceeded" in str(excinfo.value).lower()
        assert API_KEY not in caplog.text

    def test_timeout_raises_provider_timeout(self):
        provider = _provider()
        provider.session.get.side_effect = requests.Timeout(f"read timeout api_key={API_KEY}")
        with pytest.raises(ProviderTimeoutError) as excinfo:
            provider.search(_movie_query())
        assert API_KEY not in str(excinfo.value)

    def test_invalid_json_raises(self):
        resp = _response([])
        resp.json.side_effect = ValueError("Expecting value")
        with pytest.raises(ProviderError):
            _provider(resp).search(_movie_query())

    def test_status_false_is_a_real_empty_answer(self):
        resp = _response([])
        resp.json.return_value = {"status": False, "error": "can't find movie or tv"}
        assert _provider(resp).search(_movie_query()) == []

    @pytest.mark.parametrize("exc", [ProviderAuthError("x"), ProviderRateLimitError("x")])
    def test_auth_and_rate_limit_still_propagate(self, exc):
        provider = _provider()
        provider.session.get.side_effect = exc
        with pytest.raises(type(exc)):
            provider.search(_movie_query())

    def test_health_check_does_not_echo_the_key(self):
        provider = _provider()
        provider.session.get.side_effect = _conn_error()
        ok, msg = provider.health_check()
        assert ok is False
        assert API_KEY not in msg


# ---------------------------------------------------------------------------
# download()
# ---------------------------------------------------------------------------


def _zip(*entries: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


def _search_one(sub: dict, query: VideoQuery) -> tuple[SubDLProvider, SubtitleResult]:
    provider = _provider(_response([sub]))
    return provider, provider.search(query)[0]


class TestDownload:
    def test_downloads_the_subtitle_url_without_the_key(self):
        provider, result = _search_one(_subtitle(), _movie_query())
        payload = _zip(("Ratatouille.srt", _SRT))
        with patch("providers.subdl._stream_download", return_value=payload) as dl:
            content = provider.download(result)
        assert content == _SRT
        url = dl.call_args.args[1]
        assert url == "https://dl.subdl.com/subtitle/3389884-8312959.zip"

    def test_rar_payload_is_extracted_as_rar(self):
        provider, result = _search_one(_subtitle(), _movie_query())
        rar_payload = b"Rar!\x1a\x07\x01\x00" + b"\x00" * 32
        with (
            patch("providers.subdl._stream_download", return_value=rar_payload),
            patch(
                "providers.subdl.extract_subtitles_from_rar",
                return_value=[("Ratatouille.srt", _SRT)],
            ) as rar,
            patch("providers.subdl.extract_subtitles_from_zip") as zip_,
        ):
            provider.download(result)
        rar.assert_called_once_with(rar_payload)
        zip_.assert_not_called()

    def test_season_pack_picks_the_requested_episode(self):
        sub = _subtitle(season=1, full_season=True, url="/subtitle/1-2.zip")
        provider, result = _search_one(sub, _episode_query(episode=3))
        files = [(f"City Hunter ep{n}.srt", f"ep{n}".encode()) for n in range(1, 52)]
        with patch("providers.subdl._stream_download", return_value=_zip(*files)):
            content = provider.download(result)
        assert content == b"ep3"
        # archive_utils sanitises member names (spaces -> underscores).
        assert result.filename == "City_Hunter_ep3.srt"

    def test_anime_pack_through_real_extraction(self):
        sub = _subtitle(season=1, full_season=True, url="/subtitle/1-2.zip")
        provider, result = _search_one(sub, _episode_query(episode=3))
        files = [(f"[Grp] Show - {n:02d} [1080p].ass", f"ep{n}".encode()) for n in (1, 2, 3, 4)]
        with patch("providers.subdl._stream_download", return_value=_zip(*files)):
            assert provider.download(result) == b"ep3"

    def test_season_pack_without_the_episode_fails_instead_of_first_file(self):
        sub = _subtitle(season=1, full_season=True, url="/subtitle/1-2.zip")
        provider, result = _search_one(sub, _episode_query(series_title="Saiki K.", episode=3))
        payload = _zip(("Saiki.K.S01E01.English.Dub.srt", _SRT))
        with (
            patch("providers.subdl._stream_download", return_value=payload),
            pytest.raises(ProviderNotApplicableError, match="episode"),
        ):
            provider.download(result)


# ---------------------------------------------------------------------------
# _pick_best_subtitle()
# ---------------------------------------------------------------------------


def _files(*names: str) -> list[tuple[str, bytes]]:
    return [(n, n.encode()) for n in names]


def _pick(names: list[str], **query) -> str | None:
    picked = _pick_best_subtitle(_files(*names), VideoQuery(**query))
    return picked[0] if picked else None


class TestPickBestSubtitle:
    def test_non_padded_episode_numbers(self):
        names = ["City Hunter ep21.srt", "City Hunter ep1.srt", "City Hunter ep3.srt"]
        assert _pick(names, season=1, episode=3) == "City Hunter ep3.srt"

    def test_season_in_filename_is_respected(self):
        names = ["Show.S02E03.srt", "Show.S01E03.srt"]
        assert _pick(names, season=1, episode=3) == "Show.S01E03.srt"

    def test_other_season_alone_is_no_match(self):
        assert _pick(["Show.S02E03.srt"], season=1, episode=3) is None

    def test_e10_does_not_match_inside_e100(self):
        assert _pick(["Show E100.srt"], season=1, episode=10) is None
        assert _pick(["Show E100.srt", "Show E10.srt"], season=1, episode=10) == "Show E10.srt"

    def test_dash_separated_and_bare_e_forms(self):
        assert _pick(["Show - 2 - x.srt", "Show - 3 - x.srt"], season=1, episode=3) == (
            "Show - 3 - x.srt"
        )
        assert _pick(["Show E2.srt", "Show E3.srt"], season=1, episode=3) == "Show E3.srt"

    def test_sanitised_member_names(self):
        names = ["Grp_Show_-_02_1080p.ass", "Grp_Show_-_03_1080p.ass"]
        assert _pick(names, season=1, episode=3) == "Grp_Show_-_03_1080p.ass"
        assert _pick(["Show_03.srt", "Show_13.srt"], season=1, episode=13) == "Show_13.srt"

    def test_anime_style_release_names(self):
        names = ["[Grp] Show - 02 [1080p].ass", "[Grp] Show - 03 [1080p].ass"]
        assert _pick(names, season=1, episode=3) == "[Grp] Show - 03 [1080p].ass"

    def test_absolute_episode_matches(self):
        names = ["Ranma ep63.srt", "Ranma ep64.srt"]
        assert _pick(names, season=4, episode=19, absolute_episode=64) == "Ranma ep64.srt"

    def test_no_matching_file_returns_none_for_episode_queries(self):
        assert _pick(["Saiki K S01E01.srt"], season=1, episode=3) is None

    def test_prefers_ass_among_matches(self):
        names = ["Show.S01E03.srt", "Show.S01E03.ass", "Show.S01E04.ass"]
        assert _pick(names, season=1, episode=3) == "Show.S01E03.ass"

    def test_movie_query_prefers_ass(self):
        assert _pick(["Movie.srt", "Movie.ass"], title="Movie") == "Movie.ass"

    def test_resolution_and_codec_are_not_episode_numbers(self):
        names = ["Show.S01E03.1920x1080.x264.srt"]
        assert _pick(names, season=1, episode=3) == names[0]

    def test_unnumbered_file_allowed_when_result_is_the_exact_episode(self):
        picked = _pick_best_subtitle(
            _files("Show.srt"), VideoQuery(season=1, episode=3), exact_episode=True
        )
        assert picked is not None and picked[0] == "Show.srt"

    def test_exact_episode_still_refuses_a_conflicting_file(self):
        picked = _pick_best_subtitle(
            _files("Show.S01E05.srt"), VideoQuery(season=1, episode=3), exact_episode=True
        )
        assert picked is None
