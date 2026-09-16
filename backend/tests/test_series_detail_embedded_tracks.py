"""Series detail counts embedded target-language tracks (Forgejo #35).

Discord #general, 2026-09-16, on 1.14.2: an episode whose embedded English ASS
satisfies the profile was listed as "No subtitle found". The detail endpoints
only looked for sidecar files; the scanner, which does probe, never created a
wanted row, so the embedded fallback had nothing to fall back to.

Embedded tracks are read from the ffprobe CACHE only — a series page lists
100+ episodes and must never start a probe per request.
"""

from unittest.mock import MagicMock

import pytest

ENG_ASS = {
    "streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "eng"}}]
}
ENG_SRT = {
    "streams": [{"codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}}]
}


def _cache(path, probe, mtime=None):
    import os

    from db.cache import set_ffprobe_cache

    set_ffprobe_cache(str(path), os.path.getmtime(path) if mtime is None else mtime, probe)


@pytest.fixture
def embedded_on(app_ctx, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "use_embedded_subs", True)
    # A cache miss must never turn into a probe.
    monkeypatch.setattr(
        "ass_probe.get_media_streams",
        MagicMock(side_effect=AssertionError("series detail must not probe")),
    )


# ── Service ──────────────────────────────────────────────────────────────────


def test_cached_embedded_tracks_are_reported_per_language(embedded_on, tmp_path):
    from services.embedded_subtitles import cached_embedded_formats

    ass_ep = tmp_path / "a.mkv"
    srt_ep = tmp_path / "b.mkv"
    uncached = tmp_path / "c.mkv"
    for p in (ass_ep, srt_ep, uncached):
        p.touch()
    _cache(ass_ep, ENG_ASS)
    _cache(srt_ep, ENG_SRT)

    result = cached_embedded_formats([str(ass_ep), str(srt_ep), str(uncached)], ["en", "de"])

    assert result == {str(ass_ep): {"en": "embedded_ass"}, str(srt_ep): {"en": "embedded_srt"}}


def test_a_stale_cache_entry_is_ignored(embedded_on, tmp_path):
    from services.embedded_subtitles import cached_embedded_formats

    ep = tmp_path / "a.mkv"
    ep.touch()
    _cache(ep, ENG_ASS, mtime=1.0)

    assert cached_embedded_formats([str(ep)], ["en"]) == {}


def test_nothing_is_reported_when_embedded_tracks_are_off(embedded_on, tmp_path, monkeypatch):
    from config import get_settings
    from services.embedded_subtitles import cached_embedded_formats

    monkeypatch.setattr(get_settings(), "use_embedded_subs", False)
    ep = tmp_path / "a.mkv"
    ep.touch()
    _cache(ep, ENG_ASS)

    assert cached_embedded_formats([str(ep)], ["en"]) == {}


@pytest.mark.parametrize(
    ("sidecar", "embedded", "expected"),
    [
        ("ass", "embedded_ass", "ass"),
        ("srt", "embedded_ass", "embedded_ass"),
        ("srt", "embedded_srt", "srt"),
        ("", "embedded_srt", "embedded_srt"),
        ("", None, ""),
    ],
)
def test_sidecar_and_embedded_results_merge_like_the_scanner(sidecar, embedded, expected):
    from services.embedded_subtitles import merge_subtitle_format

    assert merge_subtitle_format(sidecar, embedded) == expected


# ── Endpoints ────────────────────────────────────────────────────────────────


def test_standalone_series_detail_shows_the_embedded_track(embedded_on, tmp_path, monkeypatch):
    from config import get_settings
    from db.standalone import upsert_standalone_series
    from routes.library.series import _get_standalone_series_detail

    monkeypatch.setattr(
        "db.profiles.get_default_profile",
        lambda: {"target_languages": ["en"], "target_language_names": ["English"]},
    )
    folder = tmp_path / "Show"
    folder.mkdir()
    ep = folder / "Show - S01E01.mkv"
    ep.touch()
    _cache(ep, ENG_ASS)
    series_id = upsert_standalone_series(title="Show", folder_path=str(folder))

    detail = _get_standalone_series_detail(series_id, get_settings())

    assert detail["episodes"], detail
    assert detail["episodes"][0]["subtitles"]["en"] == "embedded_ass"


def test_sonarr_series_detail_shows_the_embedded_track(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "use_embedded_subs", True)
    monkeypatch.setattr(
        "ass_probe.get_media_streams",
        MagicMock(side_effect=AssertionError("series detail must not probe")),
    )
    ep = tmp_path / "Show - S01E01.mkv"
    ep.touch()
    _cache(ep, ENG_ASS)

    sonarr = MagicMock()
    sonarr.get_series_by_id.return_value = {"id": 7, "title": "Show", "images": []}
    sonarr.get_episodes.return_value = [
        {"id": 70, "seasonNumber": 1, "episodeNumber": 1, "hasFile": True, "episodeFileId": 700}
    ]
    sonarr.get_episode_files_by_series.return_value = {700: {"path": str(ep)}}
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: sonarr)
    monkeypatch.setattr(
        "db.profiles.get_series_profile",
        lambda series_id: {"target_languages": ["en"], "target_language_names": ["English"]},
    )
    monkeypatch.setattr("config.map_path", lambda p: p)

    resp = app_ctx.test_client().get("/api/v1/library/series/7")

    assert resp.status_code == 200, resp.get_json()
    episode = resp.get_json()["episodes"][0]
    assert episode["subtitles"]["en"] == "embedded_ass"
