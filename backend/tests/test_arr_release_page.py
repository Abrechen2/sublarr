"""Release page and frame rate from Sonarr/Radarr for the catalog bundles (#220).

CinemaZ and AvistaZ search only the release page the file was grabbed from;
subssabbz, subsunacs and titulky compare the frame rate. Both come from the
*arr: the page from the grab in the item's history (``data.nzbInfoUrl``), the
frame rate from the file's ``mediaInfo.videoFps``. Record shapes below are the
ones Sonarr v4 / Radarr v5 returned on a real install (2026-10-20).
"""

from unittest.mock import MagicMock, patch

import pytest

from providers.base import VideoQuery
from wanted_search import release_page
from wanted_search.release_page import enrich_release_page, pick_release_page

# -- history records -----------------------------------------------------------


def _grab(date, download_id, url):
    return {
        "eventType": "grabbed",
        "date": date,
        "downloadId": download_id,
        "data": {"nzbInfoUrl": url, "protocol": "2", "indexer": "x"},
    }


def _imported(date, download_id, imported_path):
    return {
        "eventType": "downloadFolderImported",
        "date": date,
        "downloadId": download_id,
        "data": {"importedPath": imported_path, "fileId": "7"},
    }


FILE = "/tv/Show/Season 01/Show - S01E02.mkv"


def test_the_page_is_the_grab_the_current_file_was_imported_from():
    records = [
        # An upgrade grabbed since, not imported yet: not the file on disk.
        _grab("2026-10-20T00:57:30Z", "NEW", "https://cinemaz.to/new"),
        _imported("2026-08-15T19:52:32Z", "OLD", "/data/tv/Show/Season 01/Show - S01E02.mkv"),
        _grab("2026-08-13T20:51:02Z", "OLD", "https://cinemaz.to/old"),
    ]
    assert pick_release_page(records, FILE) == "https://cinemaz.to/old"


def test_an_import_of_another_file_name_is_skipped_for_the_matching_one():
    records = [
        _imported("2026-10-02T00:00:00Z", "B", "/data/tv/Show/Other.mkv"),
        _grab("2026-10-01T00:00:00Z", "B", "https://cinemaz.to/b"),
        _imported("2026-09-02T00:00:00Z", "A", "/data/tv/Show/Season 01/Show - S01E02.mkv"),
        _grab("2026-09-01T00:00:00Z", "A", "https://cinemaz.to/a"),
    ]
    assert pick_release_page(records, FILE) == "https://cinemaz.to/a"


def test_a_manually_imported_file_has_no_release_page():
    # The file on disk came from no grab; the replaced HDTV grab is another cut.
    records = [
        _imported("2026-10-02T00:00:00Z", None, "/data/tv/Show/Season 01/Show - S01E02.mkv"),
        _imported("2026-09-02T00:00:00Z", "OLD", "/data/tv/Show/Season 01/Show - S01E02 HDTV.mkv"),
        _grab("2026-09-01T00:00:00Z", "OLD", "https://cinemaz.to/111-hdtv-release"),
    ]
    assert pick_release_page(records, FILE) is None


def test_an_import_whose_grab_is_gone_has_no_release_page():
    records = [
        _imported("2026-10-02T00:00:00Z", "LOST", "/data/tv/Show/Season 01/Show - S01E02.mkv"),
        _grab("2026-09-01T00:00:00Z", "OTHER", "https://cinemaz.to/other"),
    ]
    assert pick_release_page(records, FILE) is None


def test_without_a_matching_import_the_newest_grab_wins():
    records = [
        _grab("2026-08-13T20:51:02Z", "OLD", "https://cinemaz.to/old"),
        _grab("2026-10-20T00:57:30Z", "NEW", "https://cinemaz.to/new"),
    ]
    assert pick_release_page(records, FILE) == "https://cinemaz.to/new"


@pytest.mark.parametrize(
    "records",
    [
        [],
        None,
        [{"eventType": "grabbed", "data": {}}],
        [{"eventType": "grabbed"}],
        ["garbage", {"eventType": "grabbed", "data": "nope"}],
    ],
)
def test_records_without_a_page_give_none(records):
    assert pick_release_page(records, FILE) is None


# -- the enricher --------------------------------------------------------------


@pytest.fixture(autouse=True)
def _empty_cache():
    release_page.clear_cache()
    yield
    release_page.clear_cache()


def _settings(enabled="cinemaz,animetosho", hub=True):
    return MagicMock(provider_hub_enabled=hub, providers_enabled=enabled)


def _episode_item():
    return {
        "id": 1,
        "item_type": "episode",
        "file_path": FILE,
        "sonarr_series_id": 3,
        "sonarr_episode_id": 40,
        "instance_name": None,
    }


def _run(item, settings, client, query=None):
    query = query or VideoQuery(file_path=item["file_path"], season=1, episode=2)
    with (
        patch("wanted_search.release_page.get_settings", return_value=settings),
        patch("sonarr_client.get_sonarr_client", return_value=client),
        patch("radarr_client.get_radarr_client", return_value=client),
    ):
        enrich_release_page(query, item)
    return query


def _sonarr(records):
    client = MagicMock()
    client.get_episode_history.return_value = records
    return client


GRAB = [_grab("2026-10-01T00:00:00Z", "A", "https://cinemaz.to/a")]


def test_an_episode_gets_its_release_page_when_cinemaz_is_enabled():
    client = _sonarr(GRAB)
    assert _run(_episode_item(), _settings(), client).info_url == "https://cinemaz.to/a"
    client.get_episode_history.assert_called_once_with(40)


def test_a_movie_gets_its_release_page_when_avistaz_is_enabled():
    client = MagicMock()
    client.get_movie_history.return_value = GRAB
    item = {"id": 2, "item_type": "movie", "file_path": "/m/M.mkv", "radarr_movie_id": 9}
    query = _run(item, _settings("avistaz"), client, VideoQuery(file_path="/m/M.mkv", title="M"))
    assert query.info_url == "https://cinemaz.to/a"
    client.get_movie_history.assert_called_once_with(9)


@pytest.mark.parametrize(
    "settings",
    [
        _settings(hub=False),
        _settings(enabled="animetosho,jimaku"),
        _settings(enabled=""),  # empty = the defaults, which exclude opt-in catalog providers
    ],
)
def test_history_is_not_read_when_no_release_page_provider_will_search(settings):
    client = _sonarr(GRAB)
    assert _run(_episode_item(), settings, client).info_url == ""
    client.get_episode_history.assert_not_called()


def test_a_profile_that_leaves_out_both_trackers_skips_the_history():
    client = _sonarr(GRAB)
    query = VideoQuery(file_path=FILE, season=1, episode=2, allowed_providers=["animetosho"])
    _run(_episode_item(), _settings(), client, query)
    client.get_episode_history.assert_not_called()


def test_the_history_is_read_once_per_episode():
    client = _sonarr(GRAB)
    _run(_episode_item(), _settings(), client)
    assert _run(_episode_item(), _settings(), client).info_url == "https://cinemaz.to/a"
    assert client.get_episode_history.call_count == 1


def test_a_failing_history_never_breaks_the_search():
    client = MagicMock()
    client.get_episode_history.side_effect = RuntimeError("sonarr down")
    assert _run(_episode_item(), _settings(), client).info_url == ""


def test_an_item_without_arr_ids_is_left_alone():
    client = _sonarr(GRAB)
    item = {"id": 5, "item_type": "episode", "file_path": FILE, "standalone_series_id": 1}
    assert _run(item, _settings(), client).info_url == ""
    client.get_episode_history.assert_not_called()


# -- the clients ---------------------------------------------------------------


def _client(module_name, cls_name):
    module = __import__(module_name)
    client = getattr(module, cls_name)("http://arr:1", "k")
    client._get = MagicMock()
    return client


def test_sonarr_episode_history_reads_the_paged_records():
    client = _client("sonarr_client", "SonarrClient")
    client._get.return_value = {"page": 1, "records": GRAB, "totalRecords": 1}
    assert client.get_episode_history(40) == GRAB
    path, kwargs = client._get.call_args.args[0], client._get.call_args.kwargs
    assert path == "/history"
    assert kwargs["params"]["episodeId"] == 40


@pytest.mark.parametrize("answer", [None, {}, {"records": None}, "x"])
def test_sonarr_episode_history_survives_odd_answers(answer):
    client = _client("sonarr_client", "SonarrClient")
    client._get.return_value = answer
    assert client.get_episode_history(40) == []


def test_radarr_movie_history_reads_the_plain_list():
    client = _client("radarr_client", "RadarrClient")
    client._get.return_value = GRAB
    assert client.get_movie_history(9) == GRAB
    assert client._get.call_args.args[0] == "/history/movie"
    assert client._get.call_args.kwargs["params"] == {"movieId": 9}
    client._get.return_value = None
    assert client.get_movie_history(9) == []


def test_sonarr_metadata_carries_the_file_frame_rate():
    client = _client("sonarr_client", "SonarrClient")
    series = {"id": 3, "title": "Show", "tvdbId": 1, "customFields": {}}
    episode = {
        "id": 40,
        "seasonNumber": 1,
        "episodeNumber": 2,
        "episodeFile": {"mediaInfo": {"videoFps": 23.976}},
    }
    client._get.side_effect = lambda path, **_kw: series if path.startswith("/series") else episode
    with patch.dict("sys.modules", {"anidb_mapper": MagicMock(get_anidb_id=lambda **_k: None)}):
        assert client.get_episode_metadata(3, 40)["fps"] == 23.976


def test_radarr_metadata_carries_the_file_frame_rate():
    client = _client("radarr_client", "RadarrClient")
    client._get.return_value = {"title": "M", "movieFile": {"mediaInfo": {"videoFps": 25}}}
    assert client.get_movie_metadata(9)["fps"] == 25.0
    client._get.return_value = {"title": "M"}
    assert client.get_movie_metadata(9)["fps"] is None


@pytest.mark.parametrize("value", [0, "", None, "abc", -1])
def test_an_unknown_frame_rate_is_none(value):
    client = _client("radarr_client", "RadarrClient")
    client._get.return_value = {"title": "M", "movieFile": {"mediaInfo": {"videoFps": value}}}
    assert client.get_movie_metadata(9)["fps"] is None


def test_the_sonarr_enricher_puts_the_frame_rate_on_the_query():
    from wanted_search.metadata_enrichers import _enrich_from_radarr, _enrich_from_sonarr

    client = MagicMock()
    client.get_episode_metadata.return_value = {"season": 1, "episode": 2, "fps": 23.976}
    client.get_movie_metadata.return_value = {"title": "M", "fps": 25.0}
    with (
        patch("sonarr_client.get_sonarr_client", return_value=client),
        patch("radarr_client.get_radarr_client", return_value=client),
    ):
        episode_query, movie_query = VideoQuery(), VideoQuery()
        assert _enrich_from_sonarr(episode_query, _episode_item())
        assert _enrich_from_radarr(movie_query, {"id": 2, "radarr_movie_id": 9})
    assert episode_query.fps == 23.976
    assert movie_query.fps == 25.0


def test_a_wanted_episode_query_carries_the_release_page_and_frame_rate():
    from wanted_search.metadata import build_query_from_wanted

    client = _sonarr(GRAB)
    client.get_episode_metadata.return_value = {
        "series_title": "Show",
        "season": 1,
        "episode": 2,
        "anidb_id": 1,  # skips the Shoko lookup
        "fps": 23.976,
    }
    settings = _settings()
    settings.target_language = "de"
    with (
        patch("wanted_search.metadata.get_settings", return_value=settings),
        patch("wanted_search.release_page.get_settings", return_value=settings),
        patch("sonarr_client.get_sonarr_client", return_value=client),
    ):
        query = build_query_from_wanted(_episode_item())
    assert query.info_url == "https://cinemaz.to/a"
    assert query.fps == 23.976
