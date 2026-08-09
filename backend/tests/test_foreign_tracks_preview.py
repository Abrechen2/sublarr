"""Preview and manual-run behaviour for the foreign-track rule."""

import os

import pytest

from db.models import foreign_tracks as ft


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
    from app import create_app
    from config import reload_settings

    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        try:
            yield application
        finally:
            # Same teardown the conftest fixtures do: without it every test in
            # this file leaks its event-dispatcher threads.
            from app_shutdown import shutdown_event_dispatchers

            shutdown_event_dispatchers(application)

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


def _make_rule(name="Foreign-Track Cleanup"):
    """`config_json` is stored as a JSON *string*, not a dict."""
    import json

    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rule = repo.create_rule(
        name=name,
        rule_type="foreign_tracks",
        enabled=True,
        config_json=json.dumps({"keep_languages": ["de", "en"]}),
    )
    return rule["id"]


def test_preview_reports_counts_from_the_scan_table(app):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.cleanup_rule_runner import _preview_by_rule

    rule_id = _make_rule()
    scan = ForeignTrackScanRepository()
    scan.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    scan.mark_probed("/media/a.mkv", ["spa", "ita"])
    scan.upsert_seen("/media/b.mkv", 1, 1.0, generation=1)
    scan.mark_probed("/media/b.mkv", [])

    result = _preview_by_rule({"rule_id": rule_id}, "/media")
    assert result["affected_files"] == 1
    assert result["clean_files"] == 1
    assert result["examples"][0]["path"] == "/media/a.mkv"
    assert result["examples"][0]["langs"] == ["ita", "spa"]


def test_preview_says_so_when_no_scan_has_run(app):
    from services.cleanup_rule_runner import _preview_by_rule

    rule_id = _make_rule()
    result = _preview_by_rule({"rule_id": rule_id}, "/media")
    assert result["affected_files"] == 0
    assert "no scan" in result["message"].lower()


def test_preview_no_longer_claims_it_is_unavailable(app):
    from services.cleanup_rule_runner import _preview_by_rule

    rule_id = _make_rule()
    result = _preview_by_rule({"rule_id": rule_id}, "/media")
    assert "not available" not in result["message"].lower()


def test_manual_run_executes_one_slice_and_reports_the_remainder(app, monkeypatch):
    from services import cleanup_rule_runner as runner

    rule_id = _make_rule()
    monkeypatch.setattr(
        runner,
        "_run_foreign_track_slice",
        lambda media_path, config: {
            "phase": "strip",
            "stripped_files": 3,
            "tracks_removed": 9,
            "bytes_freed": 100,
            "pending": 5,
            "affected": 7,
            "paused_reason": None,
        },
    )
    out = runner.execute_rule(rule_id)
    assert out["status"] == "ok"
    assert out["result"]["stripped_files"] == 3
    assert out["result"]["affected"] == 7


def test_a_paused_slice_is_reported_as_aborted(app, monkeypatch):
    from db.repositories.cleanup import CleanupRepository
    from services import cleanup_rule_runner as runner

    rule_id = _make_rule()
    monkeypatch.setattr(
        runner,
        "_run_foreign_track_slice",
        lambda media_path, config: {
            "phase": "strip",
            "stripped_files": 0,
            "tracks_removed": 0,
            "bytes_freed": 0,
            "pending": 0,
            "affected": 4,
            "paused_reason": "disk floor reached",
        },
    )
    out = runner.execute_rule(rule_id)
    assert out["status"] == "aborted"
    assert not CleanupRepository().get_history()["items"], (
        "a slice that swept nothing must not leave a history row — that is what "
        "makes a no-op distinguishable from a real sweep"
    )


def test_a_pause_after_real_work_still_records_what_was_swept(app, monkeypatch):
    """A pause is not the same as a no-op.

    The disk-floor check sits INSIDE the strip loop (`sweep.py`), so a slice
    can rewrite forty files and only then stop. Treating every `paused_reason`
    as "nothing happened" dropped both the history row and `last_run_at`, so
    that work became invisible. The floor is not an edge case for the first
    real sweep — it is the designed stopping condition (16.85 TB affected
    against 14 TB free).
    """
    from db.repositories.cleanup import CleanupRepository
    from services import cleanup_rule_runner as runner

    rule_id = _make_rule()
    monkeypatch.setattr(
        runner,
        "_run_foreign_track_slice",
        lambda media_path, config: {
            "phase": "strip",
            "stripped_files": 40,
            "tracks_removed": 91,
            "bytes_freed": 1234,
            "pending": 0,
            "affected": 300,
            "paused_reason": "disk floor reached (min_free_gb=500)",
        },
    )

    out = runner.execute_rule(rule_id)

    assert out["status"] == "aborted", "the caller must still learn that the sweep paused"
    items = CleanupRepository().get_history()["items"]
    assert [i["files_deleted"] for i in items] == [40], (
        "the forty rewritten files must appear in the cleanup history"
    )


def test_the_rule_preview_endpoint_answers_from_the_scan_table(app, monkeypatch):
    """`preview_rule` is the one the UI calls — `POST /cleanup/rules/{id}/preview`.

    It used to fall through to `execute_foreign_tracks(dry_run=True)`, which
    walks and ffprobes the whole library inside the request: 754 s and 2,825 s
    respectively on the production library. The scan table already holds every
    verdict, so the answer is a set of counts.
    """
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services import cleanup_executors
    from services import cleanup_rule_runner as runner

    def _no_walking(*args, **kwargs):
        raise AssertionError("the preview must not walk the library")

    monkeypatch.setattr(cleanup_executors, "execute_foreign_tracks", _no_walking)

    rule_id = _make_rule()
    scan = ForeignTrackScanRepository()
    scan.upsert_seen("/media/a.mkv", 1, 1.0, generation=1)
    scan.mark_probed("/media/a.mkv", ["spa", "ita"])
    scan.upsert_seen("/media/b.mkv", 1, 1.0, generation=1)
    scan.mark_probed("/media/b.mkv", [])
    scan.upsert_seen("/media/c.mkv", 1, 1.0, generation=1)
    scan.mark_probed("/media/c.mkv", ["fra"])

    preview = runner.preview_rule(rule_id)["preview"]

    # The keys PreviewPanel already renders — no frontend change needed.
    assert preview["would_strip_files"] == 2
    assert preview["would_keep"] == 1
    assert preview["would_strip_tracks"] == 3
    assert {e["path"] for e in preview["examples"]} == {"/media/a.mkv", "/media/c.mkv"}


def test_failed_rows_are_visible_in_the_preview(app):
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.cleanup_rule_runner import _preview_by_rule

    rule_id = _make_rule()
    scan = ForeignTrackScanRepository()
    scan.upsert_seen("/media/bad.mkv", 1, 1.0, generation=1)
    scan.mark_failed("/media/bad.mkv", "ffprobe exploded", ft.ERROR_VERIFY)
    result = _preview_by_rule({"rule_id": rule_id}, "/media")
    assert result["failed_files"] == 1


def test_repeated_slices_converge_to_idle_over_real_files(app, tmp_path, monkeypatch):
    """Several ticks against a real directory tree must finish the work.

    ffprobe and the remux are stubbed — the point is the state machine's
    convergence, not ffmpeg.
    """
    import os

    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks import sweep as sw
    from services.foreign_tracks.state import PHASE_IDLE

    for name in ("a.mkv", "b.mkv", "c.mkv"):
        path = tmp_path / "Show" / name
        os.makedirs(path.parent, exist_ok=True)
        path.write_bytes(b"x" * 100)
        os.utime(path, (1_000.0, 1_000.0))

    monkeypatch.setattr(
        sw,
        "_probe_file",
        lambda p: {"streams": [{"codec_type": "subtitle", "tags": {"language": "spa"}}]},
    )
    stripped = []
    monkeypatch.setattr(
        sw, "_strip_file", lambda p, keep, keep_und: (stripped.append(p), ("/trash.bak", 7))[1]
    )

    cfg = {"keep_languages": ["de", "en"], "keep_und": True, "min_free_gb": 0}
    repo = ForeignTrackScanRepository()
    for _ in range(6):
        result = sw.run_slice(str(tmp_path), cfg, budget_s=600, repo=repo)
        if result["phase"] == PHASE_IDLE:
            break

    assert result["phase"] == PHASE_IDLE
    assert len(stripped) == 3
    assert repo.counts_by_state().get("affected", 0) == 0
