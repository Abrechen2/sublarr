"""Regression: build_query_from_wanted must run once per processed item.

The enrichment pipeline behind build_query_from_wanted performs Sonarr HTTP
calls, a guessit parse, AniDB/AniList resolution and a file-hash read.
Building the source-language query used to re-run all of it.
"""

from unittest.mock import MagicMock, patch

from providers.base import VideoQuery


def _stub_query() -> VideoQuery:
    return VideoQuery(file_path="/media/show/ep1.mkv", languages=["de"], series_title="Show")


def _stub_settings():
    # Pin languages so the test does not depend on the test-env settings
    # singleton (search_wanted_item reads settings.source_language directly).
    s = MagicMock()
    s.target_language = "de"
    s.source_language = "en"
    return s


def test_search_wanted_item_builds_query_once():
    from wanted_search import search as search_mod

    manager = MagicMock()
    manager.search.return_value = []

    with (
        patch.object(
            search_mod,
            "get_wanted_item",
            return_value={
                "id": 1,
                "file_path": "/media/show/ep1.mkv",
                "item_type": "episode",
                "target_language": "de",
            },
        ),
        patch.object(search_mod, "get_settings", return_value=_stub_settings()),
        patch.object(search_mod, "get_provider_manager", return_value=manager),
        patch.object(
            search_mod, "build_query_from_wanted", side_effect=lambda item: _stub_query()
        ) as builder,
        patch.object(search_mod, "update_wanted_search"),
    ):
        search_mod.search_wanted_item(1)

    assert builder.call_count == 1, (
        f"build_query_from_wanted ran {builder.call_count}x — expected 1 "
        "(source query must be a copy, not a rebuild)"
    )


def test_search_wanted_item_source_query_language_differs():
    from wanted_search import search as search_mod

    manager = MagicMock()
    manager.search.return_value = []

    with (
        patch.object(
            search_mod,
            "get_wanted_item",
            return_value={
                "id": 1,
                "file_path": "/media/show/ep1.mkv",
                "item_type": "episode",
                "target_language": "de",
            },
        ),
        patch.object(search_mod, "get_settings", return_value=_stub_settings()),
        patch.object(search_mod, "get_provider_manager", return_value=manager),
        patch.object(search_mod, "build_query_from_wanted", side_effect=lambda item: _stub_query()),
        patch.object(search_mod, "update_wanted_search"),
    ):
        search_mod.search_wanted_item(1)

    # manager.search is called with target query (de) and source query (en) —
    # the source copy must not share the languages list with the target.
    queries = [call.args[0] for call in manager.search.call_args_list]
    langs = {tuple(q.languages) for q in queries}
    assert ("de",) in langs and langs != {("de",)}
