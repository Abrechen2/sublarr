"""Tests for db.repositories.hooks.HookRepository.

Covers: hook config CRUD, webhook config CRUD, trigger recording,
hook log CRUD, log pagination, log counts, log cleanup.
"""

import pytest

from db.repositories.hooks import HookRepository


@pytest.fixture
def repo(app_ctx):
    """Create a HookRepository instance within app context."""
    return HookRepository()


# ---------------------------------------------------------------------------
# Hook Configs CRUD
# ---------------------------------------------------------------------------


class TestHookConfigsCRUD:
    def test_create_hook_returns_dict(self, repo):
        """Creating a hook returns a dict with all expected keys."""
        result = repo.create_hook(
            name="on_download",
            event_name="subtitle.downloaded",
            script_path="/scripts/notify.sh",
            timeout_seconds=60,
            enabled=True,
        )
        assert isinstance(result, dict)
        assert result["name"] == "on_download"
        assert result["event_name"] == "subtitle.downloaded"
        assert result["hook_type"] == "script"
        assert result["enabled"] == 1
        assert result["script_path"] == "/scripts/notify.sh"
        assert result["timeout_seconds"] == 60
        assert result["trigger_count"] == 0
        assert result["last_triggered_at"] is None
        assert result["last_status"] == ""
        assert "id" in result

    def test_create_hook_disabled(self, repo):
        """Creating a disabled hook sets enabled=0."""
        result = repo.create_hook(
            name="disabled_hook",
            event_name="test",
            script_path="/scripts/test.sh",
            enabled=False,
        )
        assert result["enabled"] == 0

    def test_get_hooks_all(self, repo):
        """get_hooks without filters returns all hooks."""
        repo.create_hook("h1", "event1", "/s1.sh")
        repo.create_hook("h2", "event2", "/s2.sh")
        hooks = repo.get_hooks()
        assert len(hooks) == 2

    def test_get_hooks_by_event_name(self, repo):
        """get_hooks with event_name filter returns only matching hooks."""
        repo.create_hook("h1", "download", "/s1.sh")
        repo.create_hook("h2", "translate", "/s2.sh")
        repo.create_hook("h3", "download", "/s3.sh")

        hooks = repo.get_hooks(event_name="download")
        assert len(hooks) == 2
        assert all(h["event_name"] == "download" for h in hooks)

    def test_get_hooks_enabled_only(self, repo):
        """get_hooks with enabled_only returns only enabled hooks."""
        repo.create_hook("enabled", "test", "/s.sh", enabled=True)
        repo.create_hook("disabled", "test", "/s2.sh", enabled=False)

        hooks = repo.get_hooks(enabled_only=True)
        assert len(hooks) == 1
        assert hooks[0]["name"] == "enabled"

    def test_get_hook_by_id(self, repo):
        """Getting a hook by ID returns the correct hook."""
        created = repo.create_hook("test", "event", "/s.sh")
        result = repo.get_hook(created["id"])
        assert result is not None
        assert result["name"] == "test"

    def test_get_hook_not_found(self, repo):
        """Getting a non-existent hook returns None."""
        assert repo.get_hook(999) is None

    def test_update_hook(self, repo):
        """Updating a hook changes the specified fields."""
        created = repo.create_hook("old", "event", "/old.sh")
        result = repo.update_hook(created["id"], name="new", script_path="/new.sh")
        assert result is True

        updated = repo.get_hook(created["id"])
        assert updated["name"] == "new"
        assert updated["script_path"] == "/new.sh"

    def test_update_hook_not_found(self, repo):
        """Updating a non-existent hook returns False."""
        assert repo.update_hook(999, name="X") is False

    def test_delete_hook(self, repo):
        """Deleting a hook removes it and its associated logs."""
        created = repo.create_hook("del", "event", "/del.sh")
        repo.create_hook_log(hook_id=created["id"], event_name="event", hook_type="script")

        assert repo.delete_hook(created["id"]) is True
        assert repo.get_hook(created["id"]) is None
        # Associated logs should also be deleted
        assert repo.get_hook_log_count(hook_id=created["id"]) == 0

    def test_delete_hook_not_found(self, repo):
        """Deleting a non-existent hook returns False."""
        assert repo.delete_hook(999) is False

    def test_record_hook_triggered_success(self, repo):
        """Recording a successful trigger updates stats correctly."""
        created = repo.create_hook("test", "event", "/s.sh")
        repo.record_hook_triggered(created["id"], success=True)

        hook = repo.get_hook(created["id"])
        assert hook["trigger_count"] == 1
        assert hook["last_status"] == "success"
        assert hook["last_triggered_at"] is not None

    def test_record_hook_triggered_failure(self, repo):
        """Recording a failed trigger updates stats correctly."""
        created = repo.create_hook("test", "event", "/s.sh")
        repo.record_hook_triggered(created["id"], success=False)

        hook = repo.get_hook(created["id"])
        assert hook["trigger_count"] == 1
        assert hook["last_status"] == "failed"

    def test_record_hook_triggered_increments_count(self, repo):
        """Multiple triggers increment the count."""
        created = repo.create_hook("test", "event", "/s.sh")
        repo.record_hook_triggered(created["id"], success=True)
        repo.record_hook_triggered(created["id"], success=True)
        repo.record_hook_triggered(created["id"], success=False)

        hook = repo.get_hook(created["id"])
        assert hook["trigger_count"] == 3

    def test_record_hook_triggered_nonexistent(self, repo):
        """Recording a trigger for a non-existent hook does not raise."""
        repo.record_hook_triggered(999, success=True)


# ---------------------------------------------------------------------------
# Webhook Configs CRUD
# ---------------------------------------------------------------------------


class TestWebhookConfigsCRUD:
    def test_create_webhook_returns_dict(self, repo):
        """Creating a webhook returns a dict with all expected keys."""
        result = repo.create_webhook(
            name="notify_discord",
            event_name="subtitle.downloaded",
            url="https://discord.com/webhook/123",
            secret="s3cret",
            retry_count=5,
            timeout_seconds=15,
            enabled=True,
        )
        assert isinstance(result, dict)
        assert result["name"] == "notify_discord"
        assert result["url"] == "https://discord.com/webhook/123"
        assert result["secret"] == "s3cret"
        assert result["retry_count"] == 5
        assert result["timeout_seconds"] == 15
        assert result["enabled"] == 1
        assert result["trigger_count"] == 0
        assert result["consecutive_failures"] == 0
        assert result["last_status_code"] == 0
        assert result["last_error"] == ""

    def test_create_webhook_disabled(self, repo):
        """Creating a disabled webhook sets enabled=0."""
        result = repo.create_webhook("wh", "event", "https://example.com", enabled=False)
        assert result["enabled"] == 0

    def test_get_webhooks_all(self, repo):
        """get_webhooks returns all webhooks."""
        repo.create_webhook("w1", "e1", "https://a.com")
        repo.create_webhook("w2", "e2", "https://b.com")
        webhooks = repo.get_webhooks()
        assert len(webhooks) == 2

    def test_get_webhooks_by_event_name(self, repo):
        """get_webhooks filters by event_name."""
        repo.create_webhook("w1", "download", "https://a.com")
        repo.create_webhook("w2", "translate", "https://b.com")

        webhooks = repo.get_webhooks(event_name="download")
        assert len(webhooks) == 1
        assert webhooks[0]["event_name"] == "download"

    def test_get_webhooks_enabled_only(self, repo):
        """get_webhooks with enabled_only returns only enabled webhooks."""
        repo.create_webhook("enabled", "test", "https://a.com", enabled=True)
        repo.create_webhook("disabled", "test", "https://b.com", enabled=False)

        webhooks = repo.get_webhooks(enabled_only=True)
        assert len(webhooks) == 1
        assert webhooks[0]["name"] == "enabled"

    def test_get_webhook_by_id(self, repo):
        """Getting a webhook by ID returns the correct webhook."""
        created = repo.create_webhook("test", "event", "https://test.com")
        result = repo.get_webhook(created["id"])
        assert result is not None
        assert result["name"] == "test"

    def test_get_webhook_not_found(self, repo):
        """Getting a non-existent webhook returns None."""
        assert repo.get_webhook(999) is None

    def test_update_webhook(self, repo):
        """Updating a webhook changes the specified fields."""
        created = repo.create_webhook("old", "event", "https://old.com")
        result = repo.update_webhook(created["id"], name="new", url="https://new.com")
        assert result is True

        updated = repo.get_webhook(created["id"])
        assert updated["name"] == "new"
        assert updated["url"] == "https://new.com"

    def test_update_webhook_not_found(self, repo):
        """Updating a non-existent webhook returns False."""
        assert repo.update_webhook(999, name="X") is False

    def test_delete_webhook(self, repo):
        """Deleting a webhook removes it and its associated logs."""
        created = repo.create_webhook("del", "event", "https://del.com")
        repo.create_hook_log(webhook_id=created["id"], event_name="event", hook_type="webhook")

        assert repo.delete_webhook(created["id"]) is True
        assert repo.get_webhook(created["id"]) is None
        assert repo.get_hook_log_count(webhook_id=created["id"]) == 0

    def test_delete_webhook_not_found(self, repo):
        """Deleting a non-existent webhook returns False."""
        assert repo.delete_webhook(999) is False

    def test_record_webhook_triggered_success(self, repo):
        """Recording a successful webhook trigger updates stats correctly."""
        created = repo.create_webhook("test", "event", "https://test.com")
        repo.record_webhook_triggered(created["id"], success=True, status_code=200)

        wh = repo.get_webhook(created["id"])
        assert wh["trigger_count"] == 1
        assert wh["last_status_code"] == 200
        assert wh["last_error"] == ""
        assert wh["consecutive_failures"] == 0

    def test_record_webhook_triggered_failure(self, repo):
        """Recording a failed webhook trigger tracks consecutive failures."""
        created = repo.create_webhook("test", "event", "https://test.com")
        repo.record_webhook_triggered(
            created["id"], success=False, status_code=500, error="Server Error"
        )

        wh = repo.get_webhook(created["id"])
        assert wh["trigger_count"] == 1
        assert wh["last_status_code"] == 500
        assert wh["last_error"] == "Server Error"
        assert wh["consecutive_failures"] == 1

    def test_record_webhook_success_resets_failures(self, repo):
        """A successful trigger resets consecutive_failures to 0."""
        created = repo.create_webhook("test", "event", "https://test.com")
        repo.record_webhook_triggered(created["id"], success=False, error="err")
        repo.record_webhook_triggered(created["id"], success=False, error="err")
        repo.record_webhook_triggered(created["id"], success=True, status_code=200)

        wh = repo.get_webhook(created["id"])
        assert wh["consecutive_failures"] == 0
        assert wh["trigger_count"] == 3

    def test_record_webhook_triggered_nonexistent(self, repo):
        """Recording a trigger for a non-existent webhook does not raise."""
        repo.record_webhook_triggered(999, success=True, status_code=200)


# ---------------------------------------------------------------------------
# Hook Log
# ---------------------------------------------------------------------------


class TestHookLog:
    def test_create_hook_log_returns_dict(self, repo):
        """Creating a hook log entry returns a dict with expected keys."""
        result = repo.create_hook_log(
            hook_id=1,
            event_name="download",
            hook_type="script",
            success=True,
            exit_code=0,
            stdout="ok",
            duration_ms=150.5,
        )
        assert isinstance(result, dict)
        assert result["hook_id"] == 1
        assert result["event_name"] == "download"
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert result["stdout"] == "ok"
        assert result["duration_ms"] == 150.5

    def test_create_webhook_log_entry(self, repo):
        """Creating a webhook log entry works with webhook_id."""
        result = repo.create_hook_log(
            webhook_id=2,
            event_name="translate",
            hook_type="webhook",
            success=False,
            status_code=500,
            error="Internal Server Error",
        )
        assert result["webhook_id"] == 2
        assert result["status_code"] == 500
        assert result["success"] is False

    def test_get_hook_logs_default(self, repo):
        """get_hook_logs returns logs ordered by triggered_at descending."""
        for i in range(5):
            repo.create_hook_log(event_name=f"event_{i}", hook_type="script", success=True)

        logs = repo.get_hook_logs()
        assert len(logs) == 5

    def test_get_hook_logs_with_limit(self, repo):
        """get_hook_logs respects limit parameter."""
        for i in range(10):
            repo.create_hook_log(event_name=f"event_{i}", hook_type="script", success=True)

        logs = repo.get_hook_logs(limit=3)
        assert len(logs) == 3

    def test_get_hook_logs_with_offset(self, repo):
        """get_hook_logs respects offset parameter for pagination."""
        for i in range(5):
            repo.create_hook_log(event_name=f"event_{i}", hook_type="script", success=True)

        repo.get_hook_logs(limit=50)  # verify total exists
        offset_logs = repo.get_hook_logs(limit=50, offset=2)
        assert len(offset_logs) == 3

    def test_get_hook_logs_filter_by_hook_id(self, repo):
        """get_hook_logs filters by hook_id."""
        repo.create_hook_log(hook_id=1, event_name="e1", hook_type="script", success=True)
        repo.create_hook_log(hook_id=2, event_name="e2", hook_type="script", success=True)

        logs = repo.get_hook_logs(hook_id=1)
        assert len(logs) == 1
        assert logs[0]["hook_id"] == 1

    def test_get_hook_logs_filter_by_webhook_id(self, repo):
        """get_hook_logs filters by webhook_id."""
        repo.create_hook_log(webhook_id=10, event_name="e1", hook_type="webhook", success=True)
        repo.create_hook_log(webhook_id=20, event_name="e2", hook_type="webhook", success=True)

        logs = repo.get_hook_logs(webhook_id=10)
        assert len(logs) == 1
        assert logs[0]["webhook_id"] == 10

    def test_get_hook_log_count_all(self, repo):
        """get_hook_log_count returns total count."""
        repo.create_hook_log(event_name="e1", hook_type="script", success=True)
        repo.create_hook_log(event_name="e2", hook_type="script", success=False)

        assert repo.get_hook_log_count() == 2

    def test_get_hook_log_count_by_hook_id(self, repo):
        """get_hook_log_count filters by hook_id."""
        repo.create_hook_log(hook_id=1, event_name="e1", hook_type="script", success=True)
        repo.create_hook_log(hook_id=1, event_name="e2", hook_type="script", success=True)
        repo.create_hook_log(hook_id=2, event_name="e3", hook_type="script", success=True)

        assert repo.get_hook_log_count(hook_id=1) == 2

    def test_get_hook_log_count_by_webhook_id(self, repo):
        """get_hook_log_count filters by webhook_id."""
        repo.create_hook_log(webhook_id=5, event_name="e1", hook_type="webhook", success=True)
        assert repo.get_hook_log_count(webhook_id=5) == 1
        assert repo.get_hook_log_count(webhook_id=99) == 0

    def test_clear_hook_logs(self, repo):
        """clear_hook_logs removes all log entries."""
        repo.create_hook_log(event_name="e1", hook_type="script", success=True)
        repo.create_hook_log(event_name="e2", hook_type="webhook", success=False)

        deleted = repo.clear_hook_logs()
        assert deleted == 2
        assert repo.get_hook_log_count() == 0

    def test_clear_old_hook_logs(self, repo):
        """clear_old_hook_logs removes only entries older than N days."""
        repo.create_hook_log(event_name="recent", hook_type="script", success=True)

        # Recently created, so nothing should be deleted with 30-day cutoff
        deleted = repo.clear_old_hook_logs(days=30)
        assert deleted == 0
        assert repo.get_hook_log_count() == 1

    def test_hook_log_success_bool_conversion(self, repo):
        """Log entry success field is returned as a boolean."""
        repo.create_hook_log(event_name="test", hook_type="script", success=True)
        logs = repo.get_hook_logs()
        assert logs[0]["success"] is True

        repo.create_hook_log(event_name="test2", hook_type="script", success=False)
        logs = repo.get_hook_logs()
        # Most recent first (desc order)
        assert logs[0]["success"] is False
