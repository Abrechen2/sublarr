"""The disk warning in Settings → System takes effect (#61 A17)."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services import disk_warning


@pytest.fixture(autouse=True)
def _fresh_state():
    disk_warning._reported.clear()
    yield
    disk_warning._reported.clear()


def _settings(**kw):
    base = dict(
        disk_warning_threshold_percent=90,
        disk_warning_notify=True,
        config_dir="/config",
        media_path="/media",
    )
    return SimpleNamespace(**{**base, **kw})


def _usage(values):
    return patch("services.disk_safety.get_disk_usage_pct", side_effect=lambda p: values[p])


def test_a_full_folder_is_reported_once_a_day_and_notified():
    with _usage({"/config": 40.0, "/media": 95.0}), patch("notifier.send_notification") as notify:
        first = disk_warning.check_disk_warning(_settings())
        second = disk_warning.check_disk_warning(_settings())

    assert [r["path"] for r in first] == ["/media"]
    assert second == []
    notify.assert_called_once()
    assert notify.call_args.args[2] == "error"


def test_dropping_below_the_threshold_rearms_the_warning():
    s = _settings()
    with patch("notifier.send_notification"):
        with _usage({"/config": 10.0, "/media": 95.0}):
            disk_warning.check_disk_warning(s)
        with _usage({"/config": 10.0, "/media": 50.0}):
            disk_warning.check_disk_warning(s)
        with _usage({"/config": 10.0, "/media": 96.0}):
            again = disk_warning.check_disk_warning(s)

    assert [r["path"] for r in again] == ["/media"]


def test_notify_off_still_logs_but_sends_nothing():
    with _usage({"/config": 99.0, "/media": 10.0}), patch("notifier.send_notification") as notify:
        reports = disk_warning.check_disk_warning(_settings(disk_warning_notify=False))

    assert [r["path"] for r in reports] == ["/config"]
    notify.assert_not_called()


def test_the_job_is_registered():
    from services.scheduler import _build_default_jobs

    assert "disk_warning_check" in {spec.id for spec in _build_default_jobs()}
