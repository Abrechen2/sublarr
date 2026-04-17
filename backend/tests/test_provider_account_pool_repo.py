"""Tests for ProviderAccountPoolRepository (Phase 4a)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from db.models.core import ProviderAccountPool
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from extensions import db


def _make(
    provider: str = "opensubtitles",
    label: str = "primary",
    api_key: str = "k1",
    tier: str = "free",
    enabled: bool = True,
    last_429_at=None,
) -> ProviderAccountPool:
    row = ProviderAccountPool(
        provider_name=provider,
        account_label=label,
        api_key=api_key,
        tier=tier,
        enabled=enabled,
        last_429_at=last_429_at,
    )
    db.session.add(row)
    db.session.commit()
    return row


class TestRepoCRUD:
    def test_add_and_get(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="opensubtitles", label="primary", api_key="k", tier="vip")
        assert row_id > 0
        got = repo.get(row_id)
        assert got["provider_name"] == "opensubtitles"
        assert got["account_label"] == "primary"
        assert got["tier"] == "vip"
        assert got["enabled"] is True

    def test_duplicate_label_raises(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        repo.add(provider="opensubtitles", label="primary", api_key="k1", tier="free")
        with pytest.raises(Exception):  # sqlalchemy IntegrityError
            repo.add(provider="opensubtitles", label="primary", api_key="k2", tier="free")

    def test_update(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k", tier="free")
        repo.update(row_id, tier="pro", enabled=False)
        got = repo.get(row_id)
        assert got["tier"] == "pro"
        assert got["enabled"] is False

    def test_update_unknown_field_raises(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k")
        with pytest.raises(ValueError):
            repo.update(row_id, provider_name="hacked")

    def test_delete(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k", tier="free")
        repo.delete(row_id)
        assert repo.get(row_id) is None

    def test_update_unknown_id_returns_false(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        assert repo.update(99999, tier="vip") is False

    def test_update_known_id_returns_true(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        row_id = repo.add(provider="subdl", label="primary", api_key="k", tier="free")
        assert repo.update(row_id, tier="pro") is True


class TestRepoGetEnabledFor:
    def test_returns_only_enabled(self, app_ctx):
        _make(provider="os", label="p", enabled=True)
        _make(provider="os", label="b", enabled=False)
        repo = ProviderAccountPoolRepository()
        rows = repo.get_enabled_for("os")
        assert len(rows) == 1
        assert rows[0]["account_label"] == "p"

    def test_empty_for_unknown_provider(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        assert repo.get_enabled_for("ghost") == []


class TestRepoGetAllFor:
    def test_returns_enabled_and_disabled(self, app_ctx):
        _make(provider="os", label="p", enabled=True)
        _make(provider="os", label="b", enabled=False)
        repo = ProviderAccountPoolRepository()
        rows = repo.get_all_for("os")
        assert len(rows) == 2
        labels = {r["account_label"] for r in rows}
        assert labels == {"p", "b"}


class TestRepoMark429:
    def test_sets_last_429_at(self, app_ctx):
        row = _make(provider="os", label="p")
        repo = ProviderAccountPoolRepository()
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        repo.mark_429(row.id, now=now)
        got = repo.get(row.id)
        got_dt = got["last_429_at"]
        if got_dt.tzinfo is None:
            got_dt = got_dt.replace(tzinfo=UTC)
        assert got_dt == now

    def test_noop_for_unknown_id(self, app_ctx):
        repo = ProviderAccountPoolRepository()
        repo.mark_429(99999)  # must not raise


class TestRepoMarkUsed:
    def test_sets_last_used_at(self, app_ctx):
        row = _make(provider="os", label="p")
        repo = ProviderAccountPoolRepository()
        now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        repo.mark_used(row.id, now=now)
        got = repo.get(row.id)
        got_dt = got["last_used_at"]
        if got_dt.tzinfo is None:
            got_dt = got_dt.replace(tzinfo=UTC)
        assert got_dt == now
