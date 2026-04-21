"""Phase 4: scanner must enqueue the automation queue instead of extracting inline
when the master toggle is on.

Tests pin the contract in `services.wanted_scanner_sources._maybe_auto_extract`:

- Master toggle on  → enqueue row, no inline extract call.
- Master toggle off → legacy behavior (inline `_extract_embedded_sub`
  gated by `wanted_auto_extract`).
- Unknown item_id   → silently skipped.
"""

from unittest.mock import patch

import pytest

from config_settings import Settings
from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


def _make_sources():
    """Build a _WantedScanSourcesMixin instance without running its __init__.

    We only call `_maybe_auto_extract` which doesn't rely on the outer state.
    """
    from services.wanted_scanner_sources import _WantedScanSourcesMixin

    inst = _WantedScanSourcesMixin.__new__(_WantedScanSourcesMixin)
    return inst


class TestMasterToggleEnqueue:
    def test_enqueues_when_automation_enabled(self, repo, monkeypatch):
        """With subtitle_automation_enabled=True, auto-extract enqueues
        a row and does NOT call _extract_embedded_sub inline."""
        sources = _make_sources()
        fake_settings = Settings(
            subtitle_automation_enabled=True,
            wanted_auto_extract=False,
        )
        # Pretend the wanted_item lookup resolves target_language='ger'.
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._lookup_target_language",
                return_value="ger",
            ),
            patch(
                "routes.wanted.extract._extract_embedded_sub"
            ) as extract_mock,
        ):
            sources._maybe_auto_extract(1001, "/media/Anime/ep.mkv")
        # No inline extract.
        extract_mock.assert_not_called()
        # Queue row present.
        row = repo.get_by_wanted_item(1001)
        assert row is not None
        assert row["state"] == "pending"
        assert row["target_language"] == "ger"
        assert row["file_path"] == "/media/Anime/ep.mkv"

    def test_falls_back_to_legacy_when_master_off_and_legacy_on(self, monkeypatch):
        """Master toggle off + wanted_auto_extract on → inline extract (legacy)."""
        sources = _make_sources()
        fake_settings = Settings(
            subtitle_automation_enabled=False,
            wanted_auto_extract=True,
        )
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._extract_embedded_sub"
            ) as extract_mock,
        ):
            sources._maybe_auto_extract(1002, "/media/x.mkv")
        extract_mock.assert_called_once()

    def test_noop_when_both_off(self, repo, monkeypatch):
        sources = _make_sources()
        fake_settings = Settings(
            subtitle_automation_enabled=False, wanted_auto_extract=False
        )
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._extract_embedded_sub"
            ) as extract_mock,
        ):
            sources._maybe_auto_extract(1003, "/media/y.mkv")
        extract_mock.assert_not_called()
        assert repo.get_by_wanted_item(1003) is None


class TestSafety:
    def test_item_id_none_is_skipped(self):
        sources = _make_sources()
        fake_settings = Settings(subtitle_automation_enabled=True)
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._enqueue_automation"
            ) as enqueue_mock,
        ):
            sources._maybe_auto_extract(None, "/media/x.mkv")
        enqueue_mock.assert_not_called()

    def test_enqueue_failure_does_not_propagate(self, monkeypatch):
        """Scanner must not crash if enqueue fails (e.g. stale DB)."""
        sources = _make_sources()
        fake_settings = Settings(subtitle_automation_enabled=True)
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._lookup_target_language",
                return_value="ger",
            ),
            patch(
                "services.wanted_scanner_sources._enqueue_automation",
                side_effect=RuntimeError("db down"),
            ),
        ):
            # Must not raise.
            sources._maybe_auto_extract(1004, "/media/z.mkv")

    def test_missing_target_language_falls_back_to_legacy(self, monkeypatch):
        """If the wanted_item lookup returns no target_language, skip enqueue
        (can't route without knowing the desired language) and fall through
        to the legacy path if enabled."""
        sources = _make_sources()
        fake_settings = Settings(
            subtitle_automation_enabled=True, wanted_auto_extract=True
        )
        with (
            patch(
                "services.wanted_scanner_sources.get_settings",
                return_value=fake_settings,
            ),
            patch(
                "services.wanted_scanner_sources._lookup_target_language",
                return_value=None,
            ),
            patch(
                "services.wanted_scanner_sources._extract_embedded_sub"
            ) as extract_mock,
        ):
            sources._maybe_auto_extract(1005, "/media/a.mkv")
        # Fell back to legacy because enqueue would have been undefined.
        extract_mock.assert_called_once()
