"""Test: signs_cleanup default rule is seeded on first boot.

The seeding mechanism is `CleanupRepository.ensure_default_rules()`, called
from `app.py` startup. The `app_ctx` fixture runs `create_app(testing=True)`,
which exercises the full startup path, so by the time the test body executes
the rule must already exist.

Seeding is "first boot" only — a config flag (cleanup_default_rules_seeded)
records that the defaults were offered once, so a user who deletes a default
rule does not get it resurrected on the next restart.
"""


def test_default_signs_rule_seeded(app_ctx):
    """First-boot seeding includes a disabled signs_cleanup rule."""
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rules = repo.get_rules()
    types = {r["rule_type"] for r in rules}
    assert "signs_cleanup" in types, f"signs_cleanup not found in {types}"

    signs = next(r for r in rules if r["rule_type"] == "signs_cleanup")
    assert signs["enabled"] is False, "signs_cleanup must be disabled by default"
    assert signs["schedule"] == "weekly"
    cfg = signs["config_json"]
    assert cfg.get("strip_embedded") is True
    assert cfg.get("permanent_delete") is False
    # keep_languages is intentionally NOT seeded: the signs executor never
    # read it (language-agnostic last-track guard only), and seeding it
    # implied a protection that does not exist.
    assert "keep_languages" not in cfg


def test_ensure_default_rules_is_idempotent(app_ctx):
    """Calling ensure_default_rules() twice must not duplicate the signs_cleanup row."""
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    # create_app already called ensure_default_rules() once; call it two more times.
    repo.ensure_default_rules()
    repo.ensure_default_rules()
    count = sum(1 for r in repo.get_rules() if r["rule_type"] == "signs_cleanup")
    assert count == 1, f"Expected 1 signs_cleanup rule, found {count}"


def test_deleted_default_is_not_resurrected(app_ctx):
    """Once seeded, a user-deleted default rule stays deleted across reboots.

    create_app() already seeded the rule and set the seeded-once flag. Deleting
    the rule and re-running ensure_default_rules() (simulating a restart) must
    NOT recreate it.
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    signs = next(r for r in repo.get_rules() if r["rule_type"] == "signs_cleanup")
    assert repo.delete_rule(signs["id"]) is True

    # Simulate the next boot: flag is already set → seeding must be a no-op.
    repo.ensure_default_rules()

    count = sum(1 for r in repo.get_rules() if r["rule_type"] == "signs_cleanup")
    assert count == 0, "Deleted default rule must not be resurrected on next boot"
