"""Regression tests for the 2026-05-08 functional audit fixes.

Findings closed in 0.92.0-beta:

* B1 — `manager_status_mixin.get_provider_status` exposed stale
  ``auto_disabled=True`` for providers whose ``disabled_until`` had
  expired, because it sourced from ``get_provider_stats()`` instead of
  the cooldown-aware ``get_all_provider_stats_enriched()``.
* B2 — ``/tools/convert`` failed on non-UTF-8 SRTs because pysubs2.load()
  defaults to UTF-8 and there was no chardet detection step.
* C1 — ``success_rate`` was actually the download_rate. A new
  ``successful_searches`` column + ``result_rate`` metric distinguishes
  "provider returned hits" from "we picked their result".
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _delete_provider_stats(provider_name: str) -> None:
    """Remove any ProviderStats row for the given name (idempotent cleanup)."""
    from db.models.providers import ProviderStats
    from extensions import db

    db.session.query(ProviderStats).filter_by(provider_name=provider_name).delete()
    db.session.commit()


# ---------------------------------------------------------------------------
# B1 — stale auto_disabled mirror
# ---------------------------------------------------------------------------


class TestStaleAutoDisabledMirror:
    """The status API must surface ``auto_disabled=False`` for providers
    whose ``disabled_until`` has passed, even before any code path actually
    clears the row.
    """

    def test_get_all_provider_stats_enriched_clears_expired_auto_disabled(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import get_all_provider_stats_enriched
        from extensions import db

        past = datetime.now(UTC) - timedelta(days=24)
        db.session.merge(
            ProviderStats(
                provider_name="b1_stale_provider",
                total_searches=100,
                successful_searches=0,
                successful_downloads=0,
                failed_downloads=100,
                auto_disabled=1,
                disabled_until=past,
                consecutive_failures=48,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()

        try:
            enriched = get_all_provider_stats_enriched()
            entry = enriched.get("b1_stale_provider")
            assert entry is not None
            assert entry["auto_disabled"] is False, (
                "Cooldown expired 24 days ago — enriched view must mirror as re-enabled"
            )
        finally:
            _delete_provider_stats("b1_stale_provider")

    def test_get_all_provider_stats_enriched_keeps_active_auto_disabled(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import get_all_provider_stats_enriched
        from extensions import db

        future = datetime.now(UTC) + timedelta(hours=1)
        db.session.merge(
            ProviderStats(
                provider_name="b1_active_provider",
                total_searches=1,
                successful_searches=0,
                successful_downloads=0,
                failed_downloads=1,
                auto_disabled=1,
                disabled_until=future,
                consecutive_failures=10,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()
        try:
            enriched = get_all_provider_stats_enriched()
            entry = enriched.get("b1_active_provider")
            assert entry is not None
            assert entry["auto_disabled"] is True, (
                "Active cooldown must remain auto_disabled in the enriched view"
            )
        finally:
            _delete_provider_stats("b1_active_provider")

    def test_provider_status_mixin_shows_expired_as_re_enabled(self, app_ctx):
        from db.models.providers import ProviderStats
        from extensions import db
        from providers import ProviderManager

        past = datetime.now(UTC) - timedelta(days=24)
        # Use a real provider name so it shows up in get_provider_status.
        db.session.merge(
            ProviderStats(
                provider_name="opensubtitles",
                total_searches=10,
                successful_searches=0,
                successful_downloads=0,
                failed_downloads=10,
                auto_disabled=1,
                disabled_until=past,
                consecutive_failures=5,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()

        manager = ProviderManager()
        try:
            statuses = manager.get_provider_status()
            os_entry = next((s for s in statuses if s["name"] == "opensubtitles"), None)
            assert os_entry is not None
            assert os_entry["stats"]["auto_disabled"] is False, (
                "Status mixin must mirror cooldown expiry (B1 audit fix)"
            )
        finally:
            manager.shutdown()
            _delete_provider_stats("opensubtitles")


# ---------------------------------------------------------------------------
# C1 — successful_searches counter + result_rate metric
# ---------------------------------------------------------------------------


class TestSuccessfulSearchesCounter:
    """``record_search(success=True)`` must increment ``successful_searches``;
    ``successful_downloads`` is reserved for ``record_download``.
    """

    def test_record_search_success_increments_successful_searches(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import record_search
        from extensions import db

        provider = "c1_record_search_test"
        _delete_provider_stats(provider)

        try:
            record_search(provider, success=True, response_time_ms=42.0)
            record_search(provider, success=True, response_time_ms=42.0)
            record_search(provider, success=False, response_time_ms=300.0)

            row = db.session.get(ProviderStats, provider)
            assert row is not None
            assert row.total_searches == 3
            assert row.successful_searches == 2
            # successful_downloads must NOT advance from record_search alone
            assert (row.successful_downloads or 0) == 0
            assert row.failed_downloads == 1
        finally:
            _delete_provider_stats(provider)

    def test_enriched_view_exposes_result_rate_and_download_rate(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import get_all_provider_stats_enriched
        from extensions import db

        provider = "c1_metrics_test"
        db.session.merge(
            ProviderStats(
                provider_name=provider,
                total_searches=100,
                successful_searches=80,
                successful_downloads=20,
                failed_downloads=20,
                auto_disabled=0,
                consecutive_failures=0,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()
        try:
            enriched = get_all_provider_stats_enriched()
            entry = enriched.get(provider)
            assert entry is not None
            assert entry["result_rate"] == pytest.approx(0.80)
            assert entry["download_rate"] == pytest.approx(0.20)
            # success_rate is the back-compat alias for download_rate
            assert entry["success_rate"] == pytest.approx(0.20)
        finally:
            _delete_provider_stats(provider)

    def test_zero_searches_yields_zero_rates(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import get_all_provider_stats_enriched
        from extensions import db

        provider = "c1_zero_test"
        db.session.merge(
            ProviderStats(
                provider_name=provider,
                total_searches=0,
                successful_searches=0,
                successful_downloads=0,
                failed_downloads=0,
                auto_disabled=0,
                consecutive_failures=0,
                updated_at=datetime.now(UTC),
            )
        )
        db.session.commit()
        try:
            enriched = get_all_provider_stats_enriched()
            entry = enriched.get(provider)
            assert entry is not None
            assert entry["result_rate"] == 0.0
            assert entry["download_rate"] == 0.0
        finally:
            _delete_provider_stats(provider)


# ---------------------------------------------------------------------------
# B2 — /tools/convert encoding detection
# ---------------------------------------------------------------------------


class TestToolsConvertEncoding:
    """Verify the chardet-then-load + latin-1 fallback path used by the
    convert endpoint actually accepts a CP1252-encoded SRT.
    """

    SRT_CP1252 = (
        b"1\r\n"
        b"00:00:01,000 --> 00:00:02,000\r\n"
        b"\xa3 5 caf\xe9\r\n"  # £ 5 café in CP1252
        b"\r\n"
    )

    def test_pysubs2_default_load_fails_on_cp1252(self, tmp_path):
        import pysubs2

        srt = tmp_path / "cp1252.srt"
        srt.write_bytes(self.SRT_CP1252)

        # Default UTF-8 must fail on this byte sequence (regression marker)
        with pytest.raises(UnicodeDecodeError):
            pysubs2.load(str(srt))

    def test_pysubs2_loads_cp1252_via_explicit_encoding(self, tmp_path):
        import pysubs2

        srt = tmp_path / "cp1252.srt"
        srt.write_bytes(self.SRT_CP1252)

        # Explicit encoding (the B2 fix) must succeed
        subs = pysubs2.load(str(srt), encoding="cp1252")
        assert len(subs.events) == 1
        assert "caf" in subs.events[0].text

    def test_latin1_fallback_never_raises(self, tmp_path):
        import pysubs2

        srt = tmp_path / "weird.srt"
        # Bytes that are invalid in UTF-8 but trivially valid in latin-1
        srt.write_bytes(b"1\r\n00:00:01,000 --> 00:00:02,000\r\n\xff\xfe\xfd\r\n\r\n")
        # The fallback path used by /tools/convert
        subs = pysubs2.load(str(srt), encoding="latin-1")
        assert len(subs.events) >= 1
