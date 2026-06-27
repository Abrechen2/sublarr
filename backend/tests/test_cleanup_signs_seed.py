"""Test: signs_cleanup default rule is seeded on first boot.

The seeding mechanism is `CleanupRepository.ensure_default_rules()`, called
from `app.py` startup. The `app_ctx` fixture runs `create_app(testing=True)`,
which exercises the full startup path, so by the time the test body executes
the rule must already exist.
"""

import pytest


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
    assert "de" in cfg.get("keep_languages", [])
    assert "en" in cfg.get("keep_languages", [])


def test_ensure_default_rules_is_idempotent(app_ctx):
    """Calling ensure_default_rules() twice must not duplicate the signs_cleanup row."""
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    # create_app already called ensure_default_rules() once; call it two more times.
    repo.ensure_default_rules()
    repo.ensure_default_rules()
    count = sum(1 for r in repo.get_rules() if r["rule_type"] == "signs_cleanup")
    assert count == 1, f"Expected 1 signs_cleanup rule, found {count}"
