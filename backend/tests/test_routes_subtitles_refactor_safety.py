"""Refactor-safety tests for splitting routes/subtitles.py into a package.

Multiple callers (routes.tracks, routes.video_sync, routes.subtitle_processor,
routes.remux, routes.trash, cleanup_scheduler) + tests depend on these
public re-exports surviving the split:
    scan_subtitle_sidecars
    _auto_purge_old_trash
    _get_trash_root
    _read_manifest
"""

from __future__ import annotations

import pathlib

import flask

import routes.subtitles as subtitles_mod

EXPECTED_URL_RULES = {
    ("/api/v1/library/episodes/<int:ep_id>/subtitles", "GET"),
    ("/api/v1/library/movies/<int:movie_id>/subtitles", "GET"),
    ("/api/v1/library/series/<int:series_id>/subtitles", "GET"),
    ("/api/v1/library/episodes/<int:ep_id>/subtitles/upload", "POST"),
    ("/api/v1/library/movies/<int:movie_id>/subtitles/upload", "POST"),
    ("/api/v1/library/episodes/<int:ep_id>/subtitles/combine", "POST"),
    ("/api/v1/library/movies/<int:movie_id>/subtitles/combine", "POST"),
    ("/api/v1/library/subtitles/combine-batch", "POST"),
    ("/api/v1/library/subtitles", "DELETE"),
    ("/api/v1/library/series/<int:series_id>/subtitles/batch-delete", "POST"),
    ("/api/v1/library/trash", "GET"),
    ("/api/v1/library/trash/<batch_id>/restore", "POST"),
    ("/api/v1/library/trash/<batch_id>", "DELETE"),
    ("/api/v1/series/<int:series_id>/subtitles/export", "GET"),
    ("/api/v1/subtitles/download", "GET"),
}


def _collect_subtitles_rules(flask_app: flask.Flask) -> set[tuple[str, str]]:
    return {
        (rule.rule, method)
        for rule in flask_app.url_map.iter_rules()
        if rule.endpoint.startswith("subtitles.")
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}
    }


def test_bp_is_blueprint() -> None:
    assert isinstance(subtitles_mod.bp, flask.Blueprint)
    assert subtitles_mod.bp.name == "subtitles"


def test_all_expected_routes_are_registered(app_ctx) -> None:
    registered = _collect_subtitles_rules(app_ctx)
    missing = EXPECTED_URL_RULES - registered
    assert not missing, f"Routes missing after refactor: {sorted(missing)}"


def test_no_unexpected_subtitles_routes(app_ctx) -> None:
    registered = _collect_subtitles_rules(app_ctx)
    extra = registered - EXPECTED_URL_RULES
    assert not extra, f"Unexpected routes after refactor: {sorted(extra)}"


def test_public_reexports_stay_accessible() -> None:
    """External callers + tests rely on these at routes.subtitles.<name>."""
    assert callable(subtitles_mod.scan_subtitle_sidecars)
    assert callable(subtitles_mod._auto_purge_old_trash)
    assert callable(subtitles_mod._get_trash_root)
    assert callable(subtitles_mod._read_manifest)


def test_scan_subtitle_sidecars_behaviour_smoke(tmp_path) -> None:
    """Quick behaviour pin."""
    video = tmp_path / "Show.S01E01.mkv"
    video.write_bytes(b"")
    sidecar = tmp_path / "Show.S01E01.de.srt"
    sidecar.write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")

    results = subtitles_mod.scan_subtitle_sidecars(str(video))
    assert len(results) == 1
    assert results[0]["language"] == "de"
    assert results[0]["format"] == "srt"


def test_package_init_stays_small_after_split() -> None:
    backend_root = pathlib.Path(__file__).resolve().parents[1]
    init_path = backend_root / "routes" / "subtitles" / "__init__.py"
    if not init_path.exists():
        import pytest

        pytest.skip("pre-split: routes/subtitles is still a single file")
    loc = sum(1 for _ in init_path.open(encoding="utf-8"))
    assert loc < 60, (
        f"routes/subtitles/__init__.py grew to {loc} LOC. Move new code into a submodule."
    )
