"""Foreign-track sweep: global-settings inheritance, abort honesty, seeding.

Three defects made the library-wide embedded-subtitle sweep a no-op in
practice:

1. ``execute_foreign_tracks`` read ``keep_languages``/``keep_und`` ONLY from
   the rule's ``config_json`` and never fell back to the global
   ``cleanup_foreign_tracks_*`` settings. Rules are created with
   ``config_json="{}"``, so a freshly-created rule aborted with
   "empty keep_languages" — silently doing nothing.
2. Both dispatch paths stamped ``last_run_at`` even when the run aborted, so
   a no-op looked like a successful sweep in the UI.
3. No ``foreign_tracks`` rule was ever seeded, so the only path that strips
   embedded tracks from an *existing* library did not exist by default.

The explicit-empty case must still abort: an empty keep-set would strip every
subtitle track in the library. Only an ABSENT key inherits the global setting.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _probe(*_args, **_kwargs):
    """ger + eng are targets, jpn + ita are foreign, und is undetermined."""
    return {
        "streams": [
            {"codec_type": "video", "index": 0},
            {"codec_type": "subtitle", "index": 1, "tags": {"language": "ger"}},
            {"codec_type": "subtitle", "index": 2, "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "index": 3, "tags": {"language": "jpn"}},
            {"codec_type": "subtitle", "index": 4, "tags": {"language": "ita"}},
            {"codec_type": "subtitle", "index": 5, "tags": {"language": "und"}},
        ]
    }


def _settings(keep_languages, keep_und, media_path="/media"):
    return SimpleNamespace(
        cleanup_foreign_tracks_keep_languages=keep_languages,
        cleanup_foreign_tracks_keep_und=keep_und,
        media_path=media_path,
    )


# ---------------------------------------------------------------------------
# 1. Global-settings inheritance
# ---------------------------------------------------------------------------


def test_inherits_global_keep_languages_when_rule_config_omits_it(tmp_path):
    """A rule with config_json={} must inherit keep_languages from settings."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    strip = MagicMock(return_value="bak")
    with (
        patch("config.get_settings", return_value=_settings(["de", "en"], True)),
        patch("remux.get_media_streams", _probe),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        result = execute_foreign_tracks(str(tmp_path), {}, dry_run=False)

    assert result.get("aborted") is None, "empty config must inherit, not abort"
    assert result["stripped_files"] == 1
    assert result["tracks_removed"] == 2  # jpn + ita (und kept)
    kept = strip.call_args.kwargs["target_languages"]
    assert {"ger", "deu", "eng"}.issubset(kept)


def test_inherits_global_keep_und_when_rule_config_omits_it(tmp_path):
    """keep_und absent from the rule config follows the global setting."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    with (
        patch("config.get_settings", return_value=_settings(["de", "en"], False)),
        patch("remux.get_media_streams", _probe),
        patch("remux.remove_foreign_subtitle_streams", MagicMock(return_value="bak")),
    ):
        result = execute_foreign_tracks(str(tmp_path), {}, dry_run=True)

    assert result["would_strip_tracks"] == 3  # jpn + ita + und (global keep_und=False)


def test_rule_config_still_overrides_global(tmp_path):
    """An explicit rule config keeps precedence over the global setting."""
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    with (
        patch("config.get_settings", return_value=_settings(["de"], False)),
        patch("remux.get_media_streams", _probe),
        patch("remux.remove_foreign_subtitle_streams", MagicMock(return_value="bak")),
    ):
        result = execute_foreign_tracks(
            str(tmp_path), {"keep_languages": ["de", "en"], "keep_und": True}, dry_run=True
        )

    assert result["would_strip_tracks"] == 2  # rule config wins: und kept, eng kept


def test_explicit_empty_keep_languages_still_aborts(tmp_path):
    """An explicitly empty keep-set must abort even when settings would fill it.

    This is the safety boundary: falling back here would strip EVERY embedded
    subtitle track in the library.
    """
    from services.cleanup_executors import execute_foreign_tracks

    (tmp_path / "show.mkv").write_bytes(b"video")
    strip = MagicMock()
    with (
        patch("config.get_settings", return_value=_settings(["de", "en"], True)),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        result = execute_foreign_tracks(str(tmp_path), {"keep_languages": []}, dry_run=False)

    assert result["aborted"] == "empty keep_languages"
    assert result["stripped_files"] == 0
    strip.assert_not_called()


# ---------------------------------------------------------------------------
# 2. An aborted run must not be stamped as a successful run
# ---------------------------------------------------------------------------


def test_execute_rule_does_not_stamp_last_run_when_aborted(app_ctx):
    """ "Run now" on a rule that aborts must leave last_run_at NULL."""
    from db.repositories.cleanup import CleanupRepository
    from services.cleanup_rule_runner import execute_rule

    repo = CleanupRepository()
    rule = repo.create_rule(
        name="Foreign tracks (aborting)",
        rule_type="foreign_tracks",
        config_json='{"keep_languages": []}',  # explicit empty -> abort
        enabled=True,
        schedule="manual",
    )

    execute_rule(rule["id"])

    stored = repo.get_rule(rule["id"])
    assert stored["last_run_at"] is None, "aborted run must not look like a successful sweep"


def test_scheduled_run_does_not_stamp_last_run_when_aborted(app_ctx):
    """The nightly cleanup tick must not stamp last_run_at on an aborted sweep."""
    from cleanup_scheduler import _execute_cleanup
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rule = repo.create_rule(
        name="Foreign tracks (scheduled, aborting)",
        rule_type="foreign_tracks",
        config_json='{"keep_languages": []}',  # explicit empty -> abort
        enabled=True,
        schedule="weekly",
    )

    _execute_cleanup()

    stored = repo.get_rule(rule["id"])
    assert stored["last_run_at"] is None, "aborted scheduled run must not stamp last_run_at"


# ---------------------------------------------------------------------------
# 3. The sweep rule must exist at all
# ---------------------------------------------------------------------------


def test_foreign_tracks_rule_is_seeded_disabled_and_weekly(app_ctx):
    """The library-wide sweep is offered as a rule, but never auto-runs on upgrade.

    Same convention as signs_cleanup / old_subtitle_baks: a destructive rule is
    seeded DISABLED so an upgrade never silently rewrites a user's media. The
    user opts in; from then on it runs weekly without manual clicking.
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rules = repo.get_rules()
    types = {r["rule_type"] for r in rules}
    assert "foreign_tracks" in types, f"foreign_tracks rule not seeded — found {types}"

    rule = next(r for r in rules if r["rule_type"] == "foreign_tracks")
    assert rule["enabled"] is False, "destructive sweep must ship disabled"
    assert rule["schedule"] == "weekly", "once enabled it must run on its own, not 'manual'"


def test_seeded_foreign_tracks_rule_is_runnable_without_extra_config(app_ctx, tmp_path):
    """The seeded rule's empty config must resolve to a real keep-set, not an abort.

    This is the regression that made the feature dead on arrival: seeded with
    config_json="{}", the executor aborted on every run.
    """
    from db.repositories.cleanup import CleanupRepository
    from services.cleanup_executors import execute_foreign_tracks

    repo = CleanupRepository()
    rule = next(r for r in repo.get_rules() if r["rule_type"] == "foreign_tracks")

    (tmp_path / "show.mkv").write_bytes(b"video")
    with (
        patch("config.get_settings", return_value=_settings(["de", "en"], True)),
        patch("remux.get_media_streams", _probe),
        patch("remux.remove_foreign_subtitle_streams", MagicMock(return_value="bak")),
    ):
        result = execute_foreign_tracks(str(tmp_path), rule["config_json"], dry_run=True)

    assert result.get("aborted") is None
    assert result["would_strip_files"] == 1
