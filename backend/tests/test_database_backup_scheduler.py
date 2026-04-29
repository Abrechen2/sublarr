"""Tests for `start_backup_scheduler` honouring the four `backup_auto_*` config fields.

Before this audit the scheduler hardcoded interval=24h and hour=3 UTC and
ignored every config field — the four UI toggles in System Settings did
nothing. These tests pin the new behaviour.
"""

import threading
from unittest.mock import MagicMock, patch


def _settings(**overrides):
    s = MagicMock()
    s.backup_auto_enabled = False
    s.backup_auto_interval_hours = 24
    s.backup_auto_on_startup = False
    s.backup_notify_on_failure = True
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_read_auto_backup_settings_returns_disabled_defaults():
    from database_backup import _read_auto_backup_settings

    with patch("config.get_settings", return_value=_settings()):
        enabled, interval, on_startup, notify = _read_auto_backup_settings()

    assert enabled is False
    assert interval == 24
    assert on_startup is False
    assert notify is True


def test_read_auto_backup_settings_clamps_zero_interval():
    """0 / negative values must not collapse the wait loop into a busy spin."""
    from database_backup import _read_auto_backup_settings

    with patch("config.get_settings", return_value=_settings(backup_auto_interval_hours=0)):
        _, interval, _, _ = _read_auto_backup_settings()

    assert interval >= 1


def test_read_auto_backup_settings_swallows_settings_failure():
    """Settings import errors must not crash the scheduler — return safe defaults."""
    from database_backup import _read_auto_backup_settings

    with patch("config.get_settings", side_effect=RuntimeError("settings unavailable")):
        enabled, interval, on_startup, notify = _read_auto_backup_settings()

    assert enabled is False
    assert interval == 24
    assert on_startup is False
    assert notify is True


def test_label_for_picks_monthly_on_first_of_month():
    from datetime import UTC, datetime

    from database_backup import _label_for

    assert _label_for(datetime(2026, 5, 1, 12, 0, tzinfo=UTC)) == "monthly"


def test_label_for_picks_weekly_on_monday():
    from datetime import UTC, datetime

    from database_backup import _label_for

    # 2026-05-04 is a Monday but not 1st.
    assert _label_for(datetime(2026, 5, 4, 12, 0, tzinfo=UTC)) == "weekly"


def test_label_for_picks_daily_otherwise():
    from datetime import UTC, datetime

    from database_backup import _label_for

    # 2026-05-06 — Wednesday.
    assert _label_for(datetime(2026, 5, 6, 12, 0, tzinfo=UTC)) == "daily"


def test_run_one_backup_emits_notification_on_failure():
    """When `notify_on_failure=True`, a backup raise must reach send_notification."""
    from database_backup import _run_one_backup

    backup = MagicMock()
    backup.create_backup.side_effect = RuntimeError("disk full")

    sent = []

    def _capture(**kw):
        sent.append(kw)

    with patch("notifier.send_notification", side_effect=_capture):
        _run_one_backup(backup, notify_on_failure=True)

    assert len(sent) == 1
    assert sent[0]["event_type"] == "error"
    assert "disk full" in sent[0]["body"]


def test_run_one_backup_skips_notification_when_flag_off():
    from database_backup import _run_one_backup

    backup = MagicMock()
    backup.create_backup.side_effect = RuntimeError("disk full")

    with patch("notifier.send_notification") as mock_notify:
        _run_one_backup(backup, notify_on_failure=False)

    mock_notify.assert_not_called()


def test_run_one_backup_swallows_notify_errors():
    """Apprise / notifier failures must not crash the loop."""
    from database_backup import _run_one_backup

    backup = MagicMock()
    backup.create_backup.side_effect = RuntimeError("disk full")

    with patch("notifier.send_notification", side_effect=RuntimeError("apprise broken")):
        # Must not raise.
        _run_one_backup(backup, notify_on_failure=True)


def test_run_one_backup_calls_rotate_on_success():
    from database_backup import _run_one_backup

    backup = MagicMock()
    backup.create_backup.return_value = {"path": "/x.db"}

    _run_one_backup(backup, notify_on_failure=True)

    backup.create_backup.assert_called_once()
    backup.rotate.assert_called_once()


def test_run_one_backup_skips_rotate_on_failure():
    """If create_backup raises, we should not attempt to rotate."""
    from database_backup import _run_one_backup

    backup = MagicMock()
    backup.create_backup.side_effect = RuntimeError("boom")

    with patch("notifier.send_notification"):
        _run_one_backup(backup, notify_on_failure=True)

    backup.rotate.assert_not_called()


def test_start_backup_scheduler_skips_when_disabled(tmp_path):
    """With backup_auto_enabled=False the loop must NOT call create_backup."""
    import database_backup

    # Reset module state.
    database_backup._scheduler_thread = None
    database_backup._scheduler_stop.clear()

    fake_backup = MagicMock()
    fake_backup.create_backup = MagicMock()

    started = threading.Event()

    def _fake_settings():
        started.set()
        return _settings(backup_auto_enabled=False)

    with (
        patch("config.get_settings", side_effect=_fake_settings),
        patch("database_backup.DatabaseBackup", return_value=fake_backup),
        # Force a fast poll so the test doesn't hang for 60s.
        patch.object(database_backup, "_DISABLED_POLL_SECS", 0.1),
    ):
        database_backup.start_backup_scheduler(
            db_path=str(tmp_path / "db.sqlite"),
            backup_dir=str(tmp_path / "backups"),
        )

        assert started.wait(timeout=2.0)
        # Give the loop a moment to make a decision.
        threading.Event().wait(0.3)

        database_backup.stop_backup_scheduler()
        if database_backup._scheduler_thread:
            database_backup._scheduler_thread.join(timeout=2.0)

    fake_backup.create_backup.assert_not_called()


def test_start_backup_scheduler_runs_immediately_when_on_startup(tmp_path):
    """on_startup=True must trigger a backup before the first interval wait."""
    import database_backup

    database_backup._scheduler_thread = None
    database_backup._scheduler_stop.clear()

    fake_backup = MagicMock()
    fake_backup.create_backup = MagicMock(return_value={"path": "x.db"})

    backup_done = threading.Event()

    def _create(**kw):
        backup_done.set()
        return {"path": "x.db"}

    fake_backup.create_backup.side_effect = _create

    with (
        patch(
            "config.get_settings",
            return_value=_settings(backup_auto_enabled=True, backup_auto_on_startup=True),
        ),
        patch("database_backup.DatabaseBackup", return_value=fake_backup),
    ):
        database_backup.start_backup_scheduler(
            db_path=str(tmp_path / "db.sqlite"),
            backup_dir=str(tmp_path / "backups"),
        )

        assert backup_done.wait(timeout=3.0)

        database_backup.stop_backup_scheduler()
        if database_backup._scheduler_thread:
            database_backup._scheduler_thread.join(timeout=2.0)

    fake_backup.create_backup.assert_called()
    fake_backup.rotate.assert_called()


def test_start_backup_scheduler_uses_app_context_when_provided(tmp_path):
    """If `app` is given, on_startup runs inside `app.app_context()`."""
    import database_backup

    database_backup._scheduler_thread = None
    database_backup._scheduler_stop.clear()

    fake_backup = MagicMock()
    fake_backup.create_backup = MagicMock(return_value={"path": "x.db"})

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=ctx)
    ctx.__exit__ = MagicMock(return_value=False)
    fake_app = MagicMock()
    fake_app.app_context.return_value = ctx

    backup_done = threading.Event()
    fake_backup.create_backup.side_effect = lambda **kw: (backup_done.set(), {"path": "x.db"})[1]

    with (
        patch(
            "config.get_settings",
            return_value=_settings(backup_auto_enabled=True, backup_auto_on_startup=True),
        ),
        patch("database_backup.DatabaseBackup", return_value=fake_backup),
    ):
        database_backup.start_backup_scheduler(
            db_path=str(tmp_path / "db.sqlite"),
            backup_dir=str(tmp_path / "backups"),
            app=fake_app,
        )

        assert backup_done.wait(timeout=3.0)

        database_backup.stop_backup_scheduler()
        if database_backup._scheduler_thread:
            database_backup._scheduler_thread.join(timeout=2.0)

    fake_app.app_context.assert_called()
