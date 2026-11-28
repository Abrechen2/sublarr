"""Exclusions by Sonarr/Radarr tag, series type and monitored state (Forgejo #83).

Bazarr's Sonarr/Radarr settings (and the TRaSH setup guide) let a user keep
series or movies out of automatic subtitle work: by tag, by series type, or
by leaving unmonitored ones alone. All three are off by default.
"""

from types import SimpleNamespace

import pytest

from services.arr_exclusions import (
    episode_excluded,
    movie_exclusion,
    parse_list,
    series_exclusion,
)

TAGS = {1: "no-subs", 2: "anime", 3: "Kids"}


def _settings(**kw):
    base = dict(
        sonarr_exclude_tags="",
        sonarr_exclude_series_types="",
        sonarr_only_monitored=False,
        radarr_exclude_tags="",
        radarr_only_monitored=False,
    )
    return SimpleNamespace(**{**base, **kw})


def _series(**kw):
    return {"id": 7, "title": "Show", "tags": [], "seriesType": "standard", "monitored": True, **kw}


def test_parse_list_trims_lowers_and_drops_empty():
    assert parse_list(" No-Subs, kids ,,") == {"no-subs", "kids"}
    assert parse_list("") == set()
    assert parse_list(None) == set()


def test_defaults_exclude_nothing():
    s = _settings()
    assert series_exclusion(_series(tags=[1], monitored=False, seriesType="daily"), TAGS, s) is None
    assert movie_exclusion({"tags": [1], "monitored": False}, TAGS, s) is None
    assert episode_excluded({"monitored": False}, s) is False


@pytest.mark.parametrize("configured", ["no-subs", "NO-SUBS", "kids, no-subs"])
def test_series_with_an_excluded_tag(configured):
    reason = series_exclusion(_series(tags=[2, 1]), TAGS, _settings(sonarr_exclude_tags=configured))

    assert reason is not None and "no-subs" in reason


def test_tag_match_is_case_insensitive_on_the_arr_side_too():
    assert series_exclusion(_series(tags=[3]), TAGS, _settings(sonarr_exclude_tags="kids"))


def test_unknown_tag_id_is_ignored():
    assert (
        series_exclusion(_series(tags=[99]), TAGS, _settings(sonarr_exclude_tags="no-subs")) is None
    )


def test_series_type_exclusion():
    s = _settings(sonarr_exclude_series_types="anime,daily")

    assert series_exclusion(_series(seriesType="anime"), TAGS, s)
    assert series_exclusion(_series(seriesType="Daily"), TAGS, s)
    assert series_exclusion(_series(seriesType="standard"), TAGS, s) is None


def test_only_monitored_series():
    s = _settings(sonarr_only_monitored=True)

    assert series_exclusion(_series(monitored=False), TAGS, s)
    assert series_exclusion(_series(monitored=True), TAGS, s) is None


def test_only_monitored_episodes():
    s = _settings(sonarr_only_monitored=True)

    assert episode_excluded({"monitored": False}, s) is True
    assert episode_excluded({"monitored": True}, s) is False


def test_movie_tag_and_monitored():
    assert movie_exclusion(
        {"tags": [1], "monitored": True}, TAGS, _settings(radarr_exclude_tags="no-subs")
    )
    assert movie_exclusion(
        {"tags": [], "monitored": False}, TAGS, _settings(radarr_only_monitored=True)
    )
    assert (
        movie_exclusion(
            {"tags": [], "monitored": True}, TAGS, _settings(radarr_only_monitored=True)
        )
        is None
    )


def test_sonarr_settings_do_not_touch_movies():
    s = _settings(sonarr_exclude_tags="no-subs", sonarr_only_monitored=True)

    assert movie_exclusion({"tags": [1], "monitored": False}, TAGS, s) is None


def _scan_settings(**kw):
    base = dict(target_language="de", target_language_name="German")
    return _settings(**{**base, **kw})


def test_scanner_skips_an_excluded_series_without_listing_episodes(app_ctx, monkeypatch):
    from services import wanted_item_scanner as scanner

    sonarr = SimpleNamespace(
        url="http://sonarr",
        get_tags=lambda: [{"id": 1, "label": "no-subs"}],
        list_episodes=lambda sid: (_ for _ in ()).throw(AssertionError("listed episodes")),
    )
    result = scanner.scan_sonarr_series(
        sonarr, 7, _scan_settings(sonarr_exclude_tags="no-subs"), series_info=_series(tags=[1])
    )

    assert result == (0, 0, set())


def test_scanner_skips_an_excluded_movie(app_ctx):
    from services import wanted_item_scanner as scanner

    radarr = SimpleNamespace(
        url="http://radarr",
        get_tags=lambda: [],
        get_movie_file=lambda fid: (_ for _ in ()).throw(AssertionError("read the file")),
    )
    movie = {
        "id": 3,
        "title": "Film",
        "hasFile": True,
        "monitored": False,
        "tags": [],
        "movieFileId": 9,
    }

    assert scanner.scan_radarr_movie(radarr, movie, _scan_settings(radarr_only_monitored=True)) == (
        0,
        0,
        set(),
    )


@pytest.mark.parametrize(("value", "status"), [("anime, daily", 200), ("cartoon", 400)])
def test_series_type_setting_is_validated(client, value, status):
    rv = client.put("/api/v1/config", json={"sonarr_exclude_series_types": value})

    assert rv.status_code == status


def test_exclusion_settings_round_trip(client):
    rv = client.put(
        "/api/v1/config",
        json={"sonarr_exclude_tags": "no-subs", "radarr_only_monitored": True},
    )
    assert rv.status_code == 200
    config = client.get("/api/v1/config").get_json()
    assert config["sonarr_exclude_tags"] == "no-subs"
    assert config["radarr_only_monitored"] in (True, "true", "True")


def test_webhook_pipeline_skips_an_excluded_series():
    # The pipeline's direct-translate fallback never goes through the scanner,
    # so it must check the exclusion itself.
    from unittest.mock import patch

    import routes.webhooks as wh

    sonarr = SimpleNamespace(
        url="http://sonarr-wh",
        get_tags=lambda: [{"id": 1, "label": "no-subs"}],
        get_series_by_id=lambda sid: _series(tags=[1]),
    )
    settings = SimpleNamespace(
        webhook_delay_minutes=0,
        webhook_auto_scan=True,
        webhook_auto_search=False,
        webhook_auto_translate=True,
        sonarr_exclude_tags="no-subs",
    )
    with (
        patch("config.get_settings", return_value=settings),
        patch("sonarr_client.get_sonarr_client", return_value=sonarr),
        patch("routes.webhooks.emit_event"),
        patch("routes.webhooks.socketio") as sio,
        patch("db.jobs.create_job", side_effect=AssertionError("translated")),
        patch("services.wanted_scanner.get_scanner", side_effect=AssertionError("scanned")),
    ):
        wh._webhook_auto_pipeline(file_path="/tv/Show/S01E01.mkv", title="Show", series_id=7)

    payload = sio.emit.call_args.args[1]
    assert payload["steps"] == [{"skipped": "tag 'no-subs'"}]


# ── Excluded items lose their wanted rows in the scan itself ────────────────
# Leaving them to the full scan's cleanup failed on real data (RC 1.22.0-rc.1,
# 2026-11-28): excluding 131 series meant pruning more than half the rows, the
# cleanup fuse refused it, and the 1756 rows stayed. An exclusion is a
# deliberate removal, so the scan deletes the rows directly.


def _row(path, **kw):
    from db.wanted import upsert_wanted_item

    upsert_wanted_item("episode" if "sonarr_series_id" in kw else "movie", path, **kw)


def _paths():
    from db.wanted import get_wanted_items

    return {i["file_path"] for i in get_wanted_items(per_page=1000)["data"]}


def test_excluded_series_rows_are_deleted_by_the_scan(app_ctx):
    from services import wanted_item_scanner as scanner

    _row("/tv/a/e1.mkv", sonarr_series_id=7, sonarr_episode_id=1, instance_name="main")
    _row("/tv/a/e2.mkv", sonarr_series_id=7, sonarr_episode_id=2, instance_name="main")
    _row("/tv/other/e1.mkv", sonarr_series_id=8, sonarr_episode_id=3, instance_name="main")
    # Same Sonarr id on a second instance is a different series.
    _row("/tv2/a/e1.mkv", sonarr_series_id=7, sonarr_episode_id=1, instance_name="4k")
    sonarr = SimpleNamespace(url="http://sonarr", get_tags=lambda: [{"id": 1, "label": "no-subs"}])

    result = scanner.scan_sonarr_series(
        sonarr,
        7,
        _scan_settings(sonarr_exclude_tags="no-subs"),
        series_info=_series(tags=[1]),
        instance_name="main",
    )

    assert result == (0, 0, set())
    assert _paths() == {"/tv/other/e1.mkv", "/tv2/a/e1.mkv"}


def test_unmonitored_episode_rows_are_deleted_by_the_scan(app_ctx, monkeypatch):
    from services import wanted_item_scanner as scanner

    _row("/tv/a/e1.mkv", sonarr_series_id=7, sonarr_episode_id=1)
    _row("/tv/a/e2.mkv", sonarr_series_id=7, sonarr_episode_id=2)
    episodes = [
        {"id": 1, "hasFile": True, "monitored": True, "episodeFile": {"path": "/nope/e1.mkv"}},
        {"id": 2, "hasFile": True, "monitored": False, "episodeFile": {"path": "/nope/e2.mkv"}},
    ]
    sonarr = SimpleNamespace(
        url="http://sonarr", get_tags=lambda: [], list_episodes=lambda sid: episodes
    )
    monkeypatch.setattr(scanner, "get_series_profile", lambda sid: {"target_languages": ["de"]})

    scanner.scan_sonarr_series(
        sonarr,
        7,
        _scan_settings(sonarr_only_monitored=True, use_embedded_subs=False),
        series_info=_series(),
    )

    assert _paths() == {"/tv/a/e1.mkv"}


def test_excluded_movie_rows_are_deleted_by_the_scan(app_ctx):
    from services import wanted_item_scanner as scanner

    _row("/movies/a.mkv", radarr_movie_id=3)
    _row("/movies/b.mkv", radarr_movie_id=4)
    radarr = SimpleNamespace(url="http://radarr", get_tags=lambda: [])
    movie = {"id": 3, "title": "Film", "hasFile": True, "monitored": False, "tags": []}

    scanner.scan_radarr_movie(radarr, movie, _scan_settings(radarr_only_monitored=True))

    assert _paths() == {"/movies/b.mkv"}


def test_without_exclusions_no_rows_are_deleted(app_ctx):
    from services import wanted_item_scanner as scanner

    _row("/movies/a.mkv", radarr_movie_id=3)
    radarr = SimpleNamespace(
        url="http://radarr", get_tags=lambda: [], get_movie_file=lambda f: None
    )
    movie = {"id": 3, "title": "Film", "hasFile": True, "monitored": False, "tags": []}

    scanner.scan_radarr_movie(radarr, movie, _scan_settings())

    assert _paths() == {"/movies/a.mkv"}
