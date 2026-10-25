"""Standalone paths are checked before anything touches them.

Codex review of 1.18.0 (P2a/P2b): the series page, the bulk/sidecar/health
enumerators and the wanted pipeline checked containment late or not at all,
so a series folder symlinked out of ``media_path`` (``/media/Show ->
/outside/Show``) was still walked, parsed, inspected for subtitles, probed
and searched. Now an escaped owner folder is refused before enumeration and
every path (including wanted-row fallback paths) is checked before parsing,
filesystem access, episode-row creation, preflight, probe or search.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def media(app_ctx, tmp_path, monkeypatch):
    from config import reload_settings

    root = tmp_path / "media"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(root))
    reload_settings()
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    return root


def _video(path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00")
    return str(path)


def _series(folder_path: str) -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(title="Show", folder_path=folder_path, created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    return row.id


def _wanted(series_id: int, path: str, se: str = "S01E01", **extra) -> int:
    from db.wanted import upsert_wanted_item

    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=path,
        title=f"Show -- {se}",
        season_episode=se,
        missing_languages=["de"],
        target_language="de",
        instance_name="standalone",
        standalone_series_id=series_id,
        **extra,
    )
    return item_id


def _episode_rows() -> list[str]:
    from db.models.standalone import StandaloneEpisode
    from extensions import db

    return sorted(r.file_path for r in db.session.query(StandaloneEpisode).all())


@pytest.fixture
def escaped(media, tmp_path):
    """``media/Show`` is a symlink to ``outside/Show`` (one episode inside)."""
    real = tmp_path / "outside" / "Show"
    _video(real / "Season 1" / "Show - S01E01.mkv")
    link = media / "Show"
    os.symlink(real, link)
    return _series(str(link)), str(link / "Season 1" / "Show - S01E01.mkv"), str(real)


@pytest.fixture
def spies(monkeypatch):
    """Record every directory walk, name parse and subtitle inspection."""
    import os as _os

    import standalone.parser as parser
    import translator

    seen = {"walk": [], "parse": [], "detect": []}
    real_walk = _os.walk
    real_parse = parser.parse_media_file

    def walk(top, *a, **kw):
        seen["walk"].append(os.path.realpath(top))
        return real_walk(top, *a, **kw)

    def parse(path, *a, **kw):
        seen["parse"].append(path)
        return real_parse(path, *a, **kw)

    def detect(path, lang, *a, **kw):
        seen["detect"].append(path)
        return ""

    monkeypatch.setattr(_os, "walk", walk)
    monkeypatch.setattr(parser, "parse_media_file", parse)
    monkeypatch.setattr(translator, "detect_existing_target_for_lang", detect)
    return seen


def _touched_outside(seen, outside: str) -> list[str]:
    hits = []
    for key in ("walk", "parse", "detect"):
        hits += [p for p in seen[key] if os.path.realpath(p).startswith(outside)]
    return hits


# --- P2a: enumeration -------------------------------------------------------


def test_series_page_does_not_walk_an_escaped_folder(escaped, spies, tmp_path):
    from config import get_settings
    from routes.library.series import _get_standalone_series_detail

    sid, video, _ = escaped
    _wanted(sid, video)
    detail = _get_standalone_series_detail(sid, get_settings())

    assert detail is not None
    assert detail["episodes"] == []
    assert _touched_outside(spies, str(tmp_path / "outside")) == []
    assert _episode_rows() == []


def test_series_page_wanted_fallback_paths_are_filtered(media, spies, tmp_path):
    """Folder unreachable: the wanted-row fallback must not hand out paths
    outside the series folder or the media folder."""
    from config import get_settings
    from routes.library.series import _get_standalone_series_detail

    folder = media / "Gone"  # not on disk: the page falls back to wanted rows
    sid = _series(str(folder))
    inside = str(folder / "Show - S01E01.mkv")
    outside = _video(tmp_path / "outside" / "Other - S01E02.mkv")
    sneaky = str(folder / ".." / "Gone" / ".." / ".." / "outside" / "Other - S01E03.mkv")
    for se, path in (("S01E01", inside), ("S01E02", outside), ("S01E03", sneaky)):
        _wanted(sid, path, se)

    detail = _get_standalone_series_detail(sid, get_settings())
    assert [e["file_path"] for e in detail["episodes"]] == [inside]
    assert _touched_outside(spies, str(tmp_path / "outside")) == []
    assert _episode_rows() == [inside]


def test_file_symlink_out_of_an_allowed_folder_is_not_parsed(media, spies, tmp_path):
    from services.standalone_library import series_episode_files

    folder = media / "Show"
    good = _video(folder / "Show - S01E01.mkv")
    target = _video(tmp_path / "outside" / "secret.mkv")
    os.symlink(target, folder / "Show - S01E02.mkv")
    sid = _series(str(folder))

    files = series_episode_files(sid)
    assert [f.file_path for f in files] == [good]
    assert str(folder / "Show - S01E02.mkv") not in spies["parse"]
    assert _episode_rows() == [good]


def test_health_and_sidecar_enumerator_refuses_escaped_folder(escaped, spies, tmp_path):
    from services.standalone_library import series_episode_files, standalone_series_video_paths

    sid, video, _ = escaped
    _wanted(sid, video)
    assert series_episode_files(sid) == []
    assert standalone_series_video_paths(sid) == []
    assert _touched_outside(spies, str(tmp_path / "outside")) == []
    assert _episode_rows() == []


@pytest.mark.parametrize("variant", ["symlinked_media", "trailing_slash", "dot_segments"])
def test_legitimate_layouts_are_still_listed(app_ctx, tmp_path, monkeypatch, variant):
    from config import reload_settings
    from services.standalone_library import series_episode_files

    real_media = tmp_path / "real_media"
    video = _video(real_media / "Show" / "Season 1" / "Show - S01E01.mkv")
    media_setting = str(real_media)
    folder = str(real_media / "Show")
    if variant == "symlinked_media":
        os.symlink(real_media, tmp_path / "media")
        media_setting = str(tmp_path / "media")
        folder = str(tmp_path / "media" / "Show")
        video = str(tmp_path / "media" / "Show" / "Season 1" / "Show - S01E01.mkv")
    elif variant == "trailing_slash":
        media_setting += "/"
        folder += "/"
        video = os.path.join(folder, "Season 1", "Show - S01E01.mkv")
    else:
        folder = str(real_media / "Show" / "Season 1" / ".." / ".")
        video = os.path.join(folder, "Season 1", "Show - S01E01.mkv")
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", media_setting)
    reload_settings()
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)

    sid = _series(folder)
    files = series_episode_files(sid)
    assert [os.path.realpath(f.file_path) for f in files] == [os.path.realpath(video)]


# --- P2b: stored wanted rows ------------------------------------------------


def test_wanted_search_skips_an_escaped_standalone_row(escaped, monkeypatch):
    import wanted_search.process as process
    from db.wanted import get_wanted_item

    sid, video, _ = escaped
    item_id = _wanted(sid, video)

    def _boom(*a, **kw):
        raise AssertionError("touched an escaped file")

    monkeypatch.setattr(process, "_check_profile_cutoff_and_audio", _boom)
    monkeypatch.setattr(process, "_check_existing_sidecar", _boom)
    monkeypatch.setattr(process, "_search_flipped_item", _boom)
    monkeypatch.setattr("ass_utils.run_ffprobe", _boom)

    result = process.process_wanted_item(item_id)
    assert result["status"] == "skipped"
    assert "media folder" in result["reason"]
    row = get_wanted_item(item_id)
    assert row is not None and row["status"] == "wanted"


def test_interactive_search_and_download_refuse_an_escaped_row(escaped, monkeypatch):
    from wanted_search import download_specific_for_item, search_providers_for_item
    from wanted_search.search import search_wanted_item

    sid, video, _ = escaped
    item_id = _wanted(sid, video)

    def _boom(*a, **kw):
        raise AssertionError("provider search for an escaped file")

    monkeypatch.setattr("wanted_search.search.get_provider_manager", _boom)
    monkeypatch.setattr("wanted_search.post_processor.get_provider_manager", _boom)

    assert "media folder" in search_wanted_item(item_id)["error"]
    assert "media folder" in search_providers_for_item(item_id)["error"]
    result = download_specific_for_item(item_id, "p", "s", "de", False)
    assert result["success"] is False and "media folder" in result["error"]


def test_embedded_extraction_and_translation_refuse_an_escaped_row(escaped, monkeypatch):
    from services.embedded_extractor import extract_embedded_sub
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    sid, video, _ = escaped
    item_id = _wanted(sid, video)

    def _boom(*a, **kw):
        raise AssertionError("probed an escaped file")

    monkeypatch.setattr("ass_utils.get_media_streams", _boom)
    monkeypatch.setattr("wanted_search.process._fallback_translate_file", _boom)

    with pytest.raises(ValueError, match="media folder"):
        extract_embedded_sub(item_id, video)
    with pytest.raises(ValueError, match="media folder"):
        SubtitleAutomationRunner._translate_sidecar(None, item_id, video, "de")


def test_sonarr_rows_keep_the_existing_behaviour(media, monkeypatch):
    """No standalone ids: the guard stays out of the way (media_path checks at
    the call sites govern Sonarr/Radarr paths, as before)."""
    import wanted_search.process as process
    from db.wanted import upsert_wanted_item

    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path="/tv/Show/S01E01.mkv",
        title="Show",
        season_episode="S01E01",
        missing_languages=["de"],
        target_language="de",
        sonarr_series_id=7,
        sonarr_episode_id=70,
    )
    reached = []

    def _stop(item, *a, **kw):
        reached.append(item["id"])
        return {"wanted_id": item["id"], "status": "skipped", "reason": "test"}

    monkeypatch.setattr(process, "_check_profile_cutoff_and_audio", _stop)
    process.process_wanted_item(item_id)
    assert reached == [item_id]


# --- Codex round 1 ------------------------------------------------------------


def test_batch_probe_skips_an_escaped_row(escaped, monkeypatch):
    from flask import current_app

    import routes.wanted.batch_probe as bp_mod
    from db.wanted import get_wanted_item

    sid, video, _ = escaped
    item_id = _wanted(sid, video)

    def _boom(*a, **kw):
        raise AssertionError("probed an escaped file")

    monkeypatch.setattr("ass_utils.get_media_streams", _boom)
    monkeypatch.setattr(bp_mod, "_process_probe_result", _boom)
    bp_mod._run_batch_probe([get_wanted_item(item_id)], current_app._get_current_object())
    assert get_wanted_item(item_id) is not None


def test_batch_retranslate_skips_an_escaped_standalone_job(escaped, monkeypatch):
    from flask import current_app

    import routes.translate.retranslate as rt

    sid, video, real = escaped
    sidecar = os.path.join(real, "Season 1", "Show - S01E01.de.ass")
    with open(sidecar, "w") as fh:
        fh.write("x")
    job = {"id": "j1", "file_path": video, "arr_context": {"standalone_series_id": sid}}

    def _boom(*a, **kw):
        raise AssertionError("translated an escaped file")

    monkeypatch.setattr("db.jobs.get_outdated_jobs", lambda *_a, **_k: [job])
    monkeypatch.setattr("translator.translate_file", _boom)
    monkeypatch.setattr(rt, "_is_translation_enabled", lambda: True)
    monkeypatch.setattr(rt, "submit_background", lambda fn, *a, **kw: fn())
    with current_app.test_request_context():
        rt.retranslate_batch()
    assert os.path.exists(sidecar), "an external subtitle was deleted"


def test_wanted_cleanup_leaves_an_escaped_row_alone(escaped, monkeypatch):
    from db.wanted import get_wanted_item
    from services.wanted_scanner_core import WantedScanner

    sid, video, _ = escaped
    item_id = _wanted(sid, video)

    def _boom(*a, **kw):
        raise AssertionError("inspected an escaped file")

    monkeypatch.setattr("services.wanted_scanner_core.detect_existing_target_for_lang", _boom)
    WantedScanner._cleanup(WantedScanner.__new__(WantedScanner), set())
    assert get_wanted_item(item_id) is not None


def test_bulk_auto_sync_does_not_walk_an_escaped_folder(escaped, spies, tmp_path):
    from routes.video_sync import _bulk_videos_from_standalone

    sid, _, _ = escaped
    assert _bulk_videos_from_standalone(sid) == []
    assert _bulk_videos_from_standalone(None) == []
    assert _touched_outside(spies, str(tmp_path / "outside")) == []


def test_job_without_ids_under_a_watched_folder_is_detected_as_standalone(escaped):
    from db.standalone import upsert_watched_folder
    from services.standalone_library import wanted_item_path_refusal

    sid, video, _ = escaped
    folder = os.path.dirname(os.path.dirname(os.path.dirname(video)))
    upsert_watched_folder(folder)
    assert wanted_item_path_refusal({"file_path": video})
    assert wanted_item_path_refusal({"file_path": video, "sonarr_series_id": 7}) is None
    # Not under any watched folder and untagged: not standalone, unchanged.
    assert wanted_item_path_refusal({"file_path": "/tv/Show/S01E01.mkv"}) is None
