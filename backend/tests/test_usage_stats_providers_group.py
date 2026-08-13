"""The `providers` telemetry group — curation and delivery, kept apart.

`providers_enabled` in the payload core answers "which providers are in play on
this install". Because an empty allow-list means "all registered", it resolves
to the full registry for the common case — so the public chart built from it
counts how many providers Sublarr ships, not which ones anyone uses. On
2026-08-13 every provider in that chart sat at 27-30 out of 39 installs, and
the only two numbers that meant anything (subscene 18, customapi 11) were the
ones where somebody had actually curated a list.

This group reports the two things the core field cannot:

- ``curated`` / ``enabled`` — did the operator pick a subset, and which one.
  An install on the default set reports ``curated: false`` and an empty list,
  instead of being counted as having chosen all 29.
- ``delivering`` — providers that actually produced a subtitle in the last 30
  days. That is the number that says whether a provider earns its maintenance.

Names only, never counts, so the group stays inside the payload rule that every
field is an enum, bool, or bucket. The core field is deliberately left alone:
old installs keep reporting it with the old meaning, and mixing the two
semantics into one field would make the aggregate unreadable for months.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from services import usage_stats


class TestCuration:
    def test_explicit_list_is_reported_as_curated(self, monkeypatch):
        import config

        monkeypatch.setattr(
            config, "get_settings", lambda: SimpleNamespace(providers_enabled="addic7ed, subdl")
        )
        with patch.object(usage_stats, "_delivering_providers", return_value=[]):
            group = usage_stats._providers_group()

        assert group["curated"] is True
        assert group["enabled"] == ["addic7ed", "subdl"]

    def test_default_install_is_not_reported_as_having_chosen_everything(self, monkeypatch):
        """THE point of this group. The core field expands an empty allow-list
        to the whole registry; here that install must read as 'did not choose'."""
        import config

        monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(providers_enabled=""))
        with patch.object(usage_stats, "_delivering_providers", return_value=[]):
            group = usage_stats._providers_group()

        assert group["curated"] is False
        assert group["enabled"] == []

    def test_whitespace_only_list_counts_as_not_curated(self, monkeypatch):
        import config

        monkeypatch.setattr(
            config, "get_settings", lambda: SimpleNamespace(providers_enabled="   ,  , ")
        )
        with patch.object(usage_stats, "_delivering_providers", return_value=[]):
            group = usage_stats._providers_group()

        assert group["curated"] is False
        assert group["enabled"] == []


class TestDelivering:
    def test_reports_distinct_providers_that_delivered(self, app_ctx):
        from datetime import UTC, datetime, timedelta

        from db.models.providers import SubtitleDownload
        from extensions import db

        now = datetime.now(UTC)
        db.session.add_all(
            [
                _download("opensubtitles", now - timedelta(days=1)),
                _download("opensubtitles", now - timedelta(days=2)),
                _download("subdl", now - timedelta(days=3)),
            ]
        )
        db.session.commit()

        assert usage_stats._delivering_providers() == ["opensubtitles", "subdl"]

    def test_ignores_deliveries_outside_the_window(self, app_ctx):
        from datetime import UTC, datetime, timedelta

        from db.models.providers import SubtitleDownload  # noqa: F401
        from extensions import db

        now = datetime.now(UTC)
        db.session.add_all(
            [
                _download("subdl", now - timedelta(days=5)),
                _download("animetosho", now - timedelta(days=90)),
            ]
        )
        db.session.commit()

        result = usage_stats._delivering_providers()
        assert result == ["subdl"], "a provider silent for 90 days must not count as delivering"

    def test_machine_translation_is_not_a_delivering_provider(self, app_ctx):
        """Translation output carries a provider_name too; it is not a provider
        result and must not inflate the chart."""
        from datetime import UTC, datetime, timedelta

        from extensions import db

        now = datetime.now(UTC)
        db.session.add_all(
            [
                _download("opensubtitles", now - timedelta(days=1)),
                _download("deepl", now - timedelta(days=1), source="machine_translation"),
            ]
        )
        db.session.commit()

        assert usage_stats._delivering_providers() == ["opensubtitles"]

    def test_no_downloads_yields_empty_list(self, app_ctx):
        assert usage_stats._delivering_providers() == []


class TestPayloadWiring:
    def test_group_is_attached_to_the_payload(self, app_ctx):
        payload = usage_stats.build_usage_payload()

        assert "providers" in payload
        assert set(payload["providers"]) == {"curated", "enabled", "delivering"}

    def test_core_field_is_left_untouched(self, app_ctx):
        """Old installs keep reporting the old meaning; changing the core field
        would blend two semantics in one aggregate column for months."""
        payload = usage_stats.build_usage_payload()

        assert isinstance(payload["providers_enabled"], list)
        assert len(payload["providers_enabled"]) > 5, "core field still resolves to the registry"

    def test_a_failing_group_does_not_break_the_ping(self, app_ctx):
        with patch.object(usage_stats, "_providers_group", side_effect=RuntimeError("boom")):
            payload = usage_stats.build_usage_payload()

        assert "providers" not in payload
        assert payload["install_id"], "the core payload must still be sent"


def _download(provider: str, when, source: str = "provider"):
    from db.models.providers import SubtitleDownload

    return SubtitleDownload(
        provider_name=provider,
        subtitle_id=f"{provider}-{when.timestamp()}",
        language="de",
        file_path=f"/media/{provider}.de.srt",
        source=source,
        downloaded_at=when,
    )
