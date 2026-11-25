# backend/tests/test_titrari_result_filter.py
"""Titrari must only offer real subtitle links as results (Forgejo #21)."""

import pytest

from providers.base import VideoQuery
from providers.titrari import TitrariProvider

pytest.importorskip("bs4")


def _query() -> VideoQuery:
    return VideoQuery(
        series_title="Cowboy Bebop",
        title="Cowboy Bebop",
        season=1,
        episode=4,
        languages=["ro"],
    )


def _parse(html: str):
    return TitrariProvider()._parse_search_results(html, _query())


def _table(*rows: str) -> str:
    return "<table>" + "".join(f"<tr>{r}</tr>" for r in rows) + "</table>"


@pytest.mark.parametrize(
    "link",
    [
        '<a href="index.php?page=like&id=1234">Like</a>',
        '<a href="index.php?page=comentarii&id=1234">0 Comentarii</a>',
        '<a href="index.php?page=lista">Lista alfabetica</a>',
        '<a href="https://example.com/news/some-video-game-article">Some video game article</a>',
        '<a href="index.php">Acasa pagina principala</a>',
    ],
)
def test_navigation_like_and_comment_links_are_not_results(link):
    assert _parse(_table(f"<td>{link}</td>")) == []


def test_detail_link_is_still_a_result():
    html = _table(
        '<td><a href="index.php?page=detalii&id=1234">Cowboy Bebop S01E04 720p</a></td>'
        '<td><a href="index.php?page=like&id=1234">Like</a></td>'
        '<td><a href="index.php?page=comentarii&id=1234">0 Comentarii</a></td>'
    )

    results = _parse(html)

    assert len(results) == 1
    assert results[0].download_url.endswith("index.php?page=detalii&id=1234")
    assert results[0].provider_data["is_detail_page"] is True
    assert results[0].release_info == "Cowboy Bebop S01E04 720p"


def test_download_link_is_still_a_result():
    html = _table(
        '<td>Cowboy Bebop S01E04<a href="download.php?id=1234">Descarca</a>'
        '<a href="index.php?page=like&id=1234">Like</a></td>'
    )

    results = _parse(html)

    assert len(results) == 1
    assert results[0].download_url.endswith("download.php?id=1234")
    assert results[0].provider_data["is_detail_page"] is False
