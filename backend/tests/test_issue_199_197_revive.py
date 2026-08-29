"""#199 part 2 + #197 — give exhausted items a bounded second chance.

Attempt exhaustion is permanent and provider-blind. An item that burned its
attempts while a provider was broken stays parked forever, and fixing that
provider afterwards does nothing for it. Two triggers — elapsed time, and a
provider becoming usable again — share one mechanism, because both mean the
same thing: the earlier verdict is stale.
"""

from datetime import UTC, datetime, timedelta

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _seed(**kw):
    now = datetime.now(UTC)
    base = {
        "item_type": "episode",
        "title": "t",
        "file_path": "/x.mkv",
        "status": "wanted",
        "search_count": 0,
        "added_at": now,
        "updated_at": now,
    }
    base.update(kw)
    row = WantedItem(**base)
    db.session.add(row)
    db.session.commit()
    return row


class TestFindExhaustedIds:
    def test_finds_only_the_ones_that_gave_up(self, app_ctx):
        repo = WantedRepository()
        now = datetime.now(UTC)
        trying = _seed(file_path="/trying.mkv", search_count=1)
        gave_up = _seed(file_path="/gaveup.mkv", search_count=3)
        slow = _seed(
            file_path="/slow.mkv",
            search_count=3,
            failure_kind="no_result_slow",
            retry_after=now + timedelta(days=10),
        )
        try:
            found = set(repo.find_exhausted_ids(max_attempts=3))
            assert gave_up.id in found
            assert trying.id not in found
            assert slow.id not in found, "slow-mode items have not given up"
        finally:
            for r in (trying, gave_up, slow):
                db.session.delete(r)
            db.session.commit()

    def test_idle_since_excludes_recently_searched(self, app_ctx):
        repo = WantedRepository()
        now = datetime.now(UTC)
        fresh = _seed(file_path="/fresh.mkv", search_count=3, last_search_at=now)
        stale = _seed(
            file_path="/stale.mkv", search_count=3, last_search_at=now - timedelta(days=40)
        )
        try:
            found = set(
                repo.find_exhausted_ids(max_attempts=3, idle_since=now - timedelta(days=30))
            )
            assert stale.id in found
            assert fresh.id not in found
        finally:
            for r in (fresh, stale):
                db.session.delete(r)
            db.session.commit()

    def test_limit_caps_one_run(self, app_ctx):
        """A large parked backlog has to come back in slices — the reporting
        install had 869 exhausted items at once."""
        repo = WantedRepository()
        rows = [_seed(file_path=f"/cap{i}.mkv", search_count=3) for i in range(5)]
        try:
            assert len(repo.find_exhausted_ids(max_attempts=3, limit=2)) == 2
        finally:
            for r in rows:
                db.session.delete(r)
            db.session.commit()


class TestReviveByAge:
    def test_disabled_by_default_does_nothing(self, app_ctx, monkeypatch):
        """Reviving on its own schedule is a behaviour change nobody asked
        for on upgrade."""
        from services import wanted_revive

        row = _seed(
            file_path="/off.mkv",
            search_count=3,
            last_search_at=datetime.now(UTC) - timedelta(days=999),
        )
        try:
            assert wanted_revive.revive_exhausted_by_age() == 0
            db.session.refresh(row)
            assert row.search_count == 3
        finally:
            db.session.delete(row)
            db.session.commit()

    def test_enabled_revives_the_old_ones_only(self, app_ctx, monkeypatch):
        from services import wanted_revive

        now = datetime.now(UTC)
        old = _seed(file_path="/old.mkv", search_count=3, last_search_at=now - timedelta(days=90))
        recent = _seed(
            file_path="/recent.mkv", search_count=3, last_search_at=now - timedelta(days=2)
        )

        class S:
            wanted_max_search_attempts = 3
            wanted_adaptive_backoff_enabled = True
            wanted_revive_exhausted_after_days = 30
            wanted_revive_max_per_run = 200

        monkeypatch.setattr(wanted_revive, "peek_settings", lambda: S(), raising=False)
        monkeypatch.setattr("config.peek_settings", lambda: S())
        try:
            assert wanted_revive.revive_exhausted_by_age() == 1
            db.session.refresh(old)
            db.session.refresh(recent)
            assert old.search_count == 0, "the parked item is back in rotation"
            assert old.retry_after is None
            assert recent.search_count == 3, "a recent failure is not stale yet"
        finally:
            for r in (old, recent):
                db.session.delete(r)
            db.session.commit()


class TestReviveAfterProviderChange:
    def test_no_age_restriction(self, app_ctx, monkeypatch):
        """The point of #197 is retroactive effect: fixing a provider should
        help items that gave up five minutes ago as much as ones from
        months back."""
        from services import wanted_revive

        class S:
            wanted_max_search_attempts = 3
            wanted_adaptive_backoff_enabled = True
            wanted_revive_max_per_run = 200

        monkeypatch.setattr("config.peek_settings", lambda: S())
        recent = _seed(
            file_path="/justnow.mkv",
            search_count=3,
            last_search_at=datetime.now(UTC),
        )
        try:
            assert wanted_revive.revive_after_provider_change(["jimaku"]) == 1
            db.session.refresh(recent)
            assert recent.search_count == 0
        finally:
            db.session.delete(recent)
            db.session.commit()


class TestProviderKeyDetection:
    """The trigger has to fire on a provider change and stay quiet otherwise,
    or every settings save would reset the backlog."""

    def test_enabling_a_provider_counts(self, app_ctx):
        from routes.config.core import _provider_config_changed

        assert _provider_config_changed(["providers_enabled"]) is True

    def test_a_provider_credential_counts(self, app_ctx):
        from routes.config.core import _provider_config_changed

        assert _provider_config_changed(["jimaku_api_key"]) is True

    def test_derived_from_the_providers_own_fields(self, app_ctx):
        """Not a hardcoded list — a provider added later is covered without
        anyone remembering to update the detection."""
        from providers.registry import _PROVIDER_CLASSES
        from routes.config.core import _provider_keys

        declared = {
            f.get("key")
            for cls in _PROVIDER_CLASSES.values()
            for f in (getattr(cls, "config_fields", None) or [])
            if f.get("key")
        }
        assert declared, "no provider declares config_fields — detection would be empty"
        sample = sorted(declared)[0]
        assert sample in _provider_keys([sample])

    def test_an_unrelated_setting_does_not_trigger_it(self, app_ctx):
        from routes.config.core import _provider_config_changed

        assert _provider_config_changed(["interface_language", "items_per_page"]) is False

    def test_nothing_saved_does_not_trigger_it(self, app_ctx):
        from routes.config.core import _provider_config_changed

        assert _provider_config_changed([]) is False


class TestTheSettingsAreReachable:
    """Since 1.14.0 /config validates its keys against the _SettingsView
    subclasses. A setting no view declares is a setting nobody can turn on —
    the feature would ship switched off with no way to switch it on."""

    def _declared(self) -> set[str]:
        import config_views

        fields: set[str] = set()
        for name in dir(config_views):
            obj = getattr(config_views, name)
            declared = getattr(obj, "_fields", None)
            if isinstance(declared, frozenset):
                fields |= set(declared)
        return fields

    def test_the_new_keys_are_declared(self, app_ctx):
        declared = self._declared()
        assert "wanted_revive_exhausted_after_days" in declared
        assert "wanted_revive_max_per_run" in declared

    def test_the_check_would_notice_a_missing_one(self, app_ctx):
        """Guards the guard: if _declared() returned everything, the test
        above would pass for any key at all."""
        assert "definitely_not_a_setting" not in self._declared()
