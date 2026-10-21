"""OpenSubtitles must not hand an episode of another series to a query.

Prod 1.17.0-rc.5 audit: To Love-Ru S04 episodes held "Dare.To.Love.Me.S01E01",
"Kaguya.sama.Love.Is.War...S01E02" and "An.Archdemons.Dilemma.How.to.Love.Your.
Elf.Bride.S01E03". The title search for "To Love-Ru" returned other shows; the
only matches they earned were "episode" plus quality rules, because the series
check compared the query with ``feature_details.title`` — the episode's own
title — and so never credited, or rejected, any series. The API names the
series in ``parent_imdb_id`` and ``parent_title``.
"""

from unittest.mock import MagicMock

import pytest

from providers.base import VideoQuery
from providers.opensubtitles import OpenSubtitlesProvider


def _item(
    file_name, *, parent_title=None, parent_imdb=None, title="Episode title", hash_match=False
):
    feature = {"season_number": 1, "episode_number": 1, "title": title}
    if parent_title is not None:
        feature["parent_title"] = parent_title
    if parent_imdb is not None:
        feature["parent_imdb_id"] = parent_imdb
    return {
        "attributes": {
            "language": "de",
            "release": file_name,
            "moviehash_match": hash_match,
            "files": [{"file_id": abs(hash(file_name)) % 10**6, "file_name": file_name}],
            "feature_details": feature,
        }
    }


def _search(items, **query):
    provider = OpenSubtitlesProvider(api_key="test-key")
    provider.session = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": items}
    provider.session.get.return_value = resp
    defaults = dict(series_title="To Love-Ru", season=1, episode=1, languages=["de"])
    return provider.search(VideoQuery(**{**defaults, **query}))


def _names(results):
    return [r.filename for r in results]


class TestSeriesIdentity:
    def test_another_series_by_imdb_is_dropped(self):
        results = _search(
            [
                _item(
                    "Dare.To.Love.Me.S01E01.srt",
                    parent_imdb=30000001,
                    parent_title="Dare to Love Me",
                )
            ],
            imdb_id="tt1199037",
        )
        assert results == []

    def test_the_same_series_by_imdb_is_credited(self):
        results = _search(
            [_item("To.Love.Ru.S01E01.srt", parent_imdb=1199037, parent_title="To LOVE-Ru")],
            imdb_id="tt1199037",
        )
        assert _names(results) == ["To.Love.Ru.S01E01.srt"]
        assert "series" in results[0].matches

    def test_another_title_alone_proves_nothing(self):
        # "Shingeki no Kyojin" is "Attack on Titan": a title Sonarr does not list
        # is no evidence of another series. It earns no "series" match either.
        results = _search(
            [_item("Shingeki.no.Kyojin.S01E01.srt", parent_title="Shingeki no Kyojin")],
            series_title="Attack on Titan",
        )
        assert _names(results) == ["Shingeki.no.Kyojin.S01E01.srt"]
        assert "series" not in results[0].matches

    @pytest.mark.parametrize("parent", ["To LOVE-Ru", "To Love Ru", "Motto To LOVE-Ru"])
    def test_the_series_or_its_alias_by_title_is_kept(self, parent):
        results = _search(
            [_item("ToLoveRu.S01E01.srt", parent_title=parent)],
            series_aliases=[("Motto To LOVE-Ru", None, 2)],
        )
        assert _names(results) == ["ToLoveRu.S01E01.srt"]

    def test_without_parent_details_nothing_changes(self):
        results = _search([_item("Whatever.S01E01.srt")])
        assert _names(results) == ["Whatever.S01E01.srt"]

    def test_a_hash_match_is_the_file_itself(self, tmp_path):
        video = tmp_path / "To Love-Ru - S01E01.mkv"
        video.write_bytes(b"\0" * 1024)
        results = _search(
            [_item("Other.S01E01.srt", parent_title="Other Show", hash_match=True)],
            file_path=str(video),
            file_hash="0123456789abcdef",
        )
        assert _names(results) == ["Other.S01E01.srt"]
