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


# ---------------------------------------------------------------------------
# 4. Retroactive-sweep controls: path scope, disk floor, verify-then-recycle
#    (first bulk run on a 16.85 TB backlog with 14 TB free — the sweep must
#    be scopeable, must stop before it fills the array, and must be able to
#    recycle each file's backup after verifying the rewrite).
# ---------------------------------------------------------------------------


def _clean_probe(*_args, **_kwargs):
    """Post-strip container: targets + und only, no foreign tracks left."""
    return {
        "streams": [
            {"codec_type": "video", "index": 0},
            {"codec_type": "subtitle", "index": 1, "tags": {"language": "ger"}},
            {"codec_type": "subtitle", "index": 2, "tags": {"language": "eng"}},
            {"codec_type": "subtitle", "index": 3, "tags": {"language": "und"}},
        ]
    }
