# backend/tests/test_titrari_result_filter.py
"""Titrari search, result parsing and season-pack picking (Forgejo #21).

The earlier tests used invented markup and passed while the live provider
returned the site's default list for every query: the search sent a field the
site ignores, and like/comment links became results. These tests run on a
trimmed copy of a real titrari.ro search page.
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from providers.base import VideoQuery
from providers.titrari import TitrariProvider

pytest.importorskip("bs4")

_FIXTURE = Path(__file__).parent / "fixtures" / "titrari" / "search_inception.html"


def _movie() -> VideoQuery:
    return VideoQuery(title="Inception", year=2010, languages=["ro"])


def _episode(season=1, episode=4) -> VideoQuery:
    return VideoQuery(
        series_title="Breaking Bad",
        title="Breaking Bad",
        season=season,
        episode=episode,
        languages=["ro"],
    )


def _provider_with_page(html: str) -> tuple[TitrariProvider, MagicMock]:
    provider = TitrariProvider()
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=html)
    provider.session = session
    return provider, session


class TestSearchRequest:
    def test_movie_search_sends_the_title_in_the_site_form_field(self):
        provider, session = _provider_with_page("<html></html>")
        provider.search(_movie())

        params = session.get.call_args.kwargs["params"]
        # The site reads z2 (title) and z3 (language, 1 = Romanian); it ignored
        # "titlufilm" and answered every query with its default list.
        assert params["z2"] == "Inception"
        assert params["z3"] == 1
        assert params["page"] == "cautare"
        assert "titlufilm" not in params

    def test_episode_search_sends_only_the_series_title(self):
        # The site finds nothing for "Breaking Bad S01E04"; series are season packs.
        provider, session = _provider_with_page("<html></html>")
        provider.search(_episode())

        assert session.get.call_args.kwargs["params"]["z2"] == "Breaking Bad"


class TestResultParsing:
    def _results(self, query=None):
        provider, _ = _provider_with_page(_FIXTURE.read_text(encoding="utf-8"))
        return provider.search(query or _movie())

    def test_one_result_per_download_link(self):
        results = self._results()

        assert [r.download_url for r in results] == [
            "https://www.titrari.ro/get.php?id=135383",
            "https://www.titrari.ro/get.php?id=115936",
        ]

    def test_like_and_comment_links_are_not_results(self):
        urls = " ".join(r.download_url for r in self._results())

        assert "like.php" not in urls
        assert "getcomments.php" not in urls
        assert "follow.php" not in urls

    def test_release_info_has_the_title_and_the_uploader_comment(self):
        result = self._results()[0]

        assert result.release_info.startswith("Inception (2010)")
        assert len(result.release_info) > len("Inception (2010)")
        assert "Like" not in result.release_info

    def test_movie_matches_title_and_year(self):
        assert self._results()[0].matches >= {"title", "year"}

    def test_results_are_direct_downloads(self):
        result = self._results()[0]

        assert result.provider_data["is_detail_page"] is False
        assert result.subtitle_id == "titrari:135383"

    def test_page_without_download_links_has_no_results(self):
        provider, _ = _provider_with_page(
            '<table><tr><td><a href="/like.php?id=1">Like</a>'
            '<a href="/getcomments.php?id=1">0 Comentarii</a></td></tr></table>'
        )
        assert provider.search(_movie()) == []


def _pack_page(title: str, get_id: int = 500) -> str:
    return (
        "<table><tr><td><h1><a href=index.php?page=cautamainaltaparte&z5=1>"
        f"{title}</a></h1></td><td><a href=get.php?id={get_id}>Descarca</a></td></tr>"
        "</table>"
    )


class TestSeasonPacks:
    def test_season_pack_matches_series_and_season(self):
        provider, _ = _provider_with_page(_pack_page("Breaking Bad - Sezonul 1 (2008)"))
        result = provider.search(_episode(season=1))[0]

        assert {"series", "season"} <= result.matches

    def test_other_season_does_not_match_the_season(self):
        provider, _ = _provider_with_page(_pack_page("Breaking Bad - Sezonul 2 (2009)"))
        result = provider.search(_episode(season=1))[0]

        assert "season" not in result.matches

    def test_multi_season_pack_covers_the_season(self):
        provider, _ = _provider_with_page(_pack_page("Breaking Bad - Sezoanele 1-5 (2008)"))
        result = provider.search(_episode(season=3))[0]

        assert "season" in result.matches

    @staticmethod
    def _zip(*names: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name in names:
                zf.writestr(name, f"1\n00:00:01,000 --> 00:00:02,000\n{name}\n")
        return buf.getvalue()

    def _download(self, archive: bytes, season=1, episode=4, calls=None):
        provider, _ = _provider_with_page(_pack_page("Breaking Bad - Sezonul 1 (2008)"))
        result = provider.search(_episode(season=season, episode=episode))[0]
        import providers.titrari as mod

        def fake_download(*args, **kwargs):
            if calls is not None:
                calls.append(kwargs)
            return archive

        original = mod._stream_download
        mod._stream_download = fake_download
        try:
            provider.download(result)
        finally:
            mod._stream_download = original
        return result

    def test_download_sends_the_site_as_referer(self):
        # Without it get.php redirects to the listing page instead of the file.
        calls = []
        self._download(self._zip("Breaking.Bad.S01E04.srt"), calls=calls)

        assert calls[0]["headers"]["Referer"].startswith("https://www.titrari.ro/")

    def test_an_html_page_is_not_saved_as_a_subtitle(self):
        from providers.base import ProviderError

        with pytest.raises(ProviderError, match="HTML"):
            self._download(b"<!DOCTYPE HTML PUBLIC><html><body>Lista</body></html>")

    def test_download_picks_the_requested_episode_from_a_pack(self):
        archive = self._zip(
            "Breaking.Bad.S01E01.srt", "Breaking.Bad.S01E04.srt", "Breaking.Bad.S01E05.srt"
        )
        result = self._download(archive, episode=4)

        assert result.filename.endswith("S01E04.srt")
        assert b"S01E04" in result.content

    def test_download_refuses_a_pack_without_the_episode(self):
        from providers.base import ProviderError

        archive = self._zip("Breaking.Bad.S01E01.srt", "Breaking.Bad.S01E02.srt")
        with pytest.raises(ProviderError, match="S01E09"):
            self._download(archive, episode=9)
