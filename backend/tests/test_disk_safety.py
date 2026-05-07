"""Tests for services.disk_safety — disk-pressure helpers used by safety valves."""

from collections import namedtuple
from unittest.mock import patch

import pytest

from services.disk_safety import (
    format_disk_status,
    get_disk_usage_pct,
    is_disk_critical,
)

DiskUsage = namedtuple("usage", ["total", "used", "free"])


def _fake_usage(used_pct: float, total_gb: float = 100.0) -> DiskUsage:
    total = int(total_gb * 1024 * 1024 * 1024)
    used = int(total * (used_pct / 100.0))
    return DiskUsage(total=total, used=used, free=total - used)


class TestGetDiskUsagePct:
    def test_returns_used_percentage(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=42.5)):
            assert get_disk_usage_pct(str(tmp_path)) == pytest.approx(42.5, abs=0.1)

    def test_returns_none_when_path_missing(self):
        with patch("shutil.disk_usage", side_effect=FileNotFoundError("nope")):
            assert get_disk_usage_pct("/no/such/path") is None

    def test_returns_none_on_oserror(self, tmp_path):
        with patch("shutil.disk_usage", side_effect=OSError("permission denied")):
            assert get_disk_usage_pct(str(tmp_path)) is None

    def test_zero_total_returns_none(self, tmp_path):
        with patch("shutil.disk_usage", return_value=DiskUsage(total=0, used=0, free=0)):
            assert get_disk_usage_pct(str(tmp_path)) is None


class TestIsDiskCritical:
    def test_below_threshold_is_not_critical(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=80.0)):
            assert is_disk_critical(str(tmp_path), threshold_pct=98.0) is False

    def test_at_threshold_is_critical(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=98.0)):
            assert is_disk_critical(str(tmp_path), threshold_pct=98.0) is True

    def test_above_threshold_is_critical(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=99.5)):
            assert is_disk_critical(str(tmp_path), threshold_pct=98.0) is True

    def test_unreadable_path_is_not_critical(self):
        with patch("shutil.disk_usage", side_effect=FileNotFoundError("nope")):
            assert is_disk_critical("/no/such/path", threshold_pct=98.0) is False

    def test_threshold_at_or_above_100_disables_gate(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=99.99)):
            assert is_disk_critical(str(tmp_path), threshold_pct=100.0) is False
            assert is_disk_critical(str(tmp_path), threshold_pct=200.0) is False


class TestFormatDiskStatus:
    def test_formats_pct_when_known(self, tmp_path):
        with patch("shutil.disk_usage", return_value=_fake_usage(used_pct=97.0, total_gb=74.0)):
            status = format_disk_status(str(tmp_path))
            assert "97" in status
            assert "%" in status

    def test_handles_unknown_path(self):
        with patch("shutil.disk_usage", side_effect=FileNotFoundError("nope")):
            assert format_disk_status("/no/such/path") == "unknown"
