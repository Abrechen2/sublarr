"""CRUD + helpers for the provider_account_pools table (Phase 4a)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from db.models.core import ProviderAccountPool
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


def _as_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=UTC)
    return value


class ProviderAccountPoolRepository(BaseRepository):
    """Row-per-API-key CRUD + runtime helpers."""

    def _row_to_dict(self, row: ProviderAccountPool) -> dict:
        return {
            "id": row.id,
            "provider_name": row.provider_name,
            "account_label": row.account_label,
            "api_key": row.api_key,
            "username": row.username,
            "password": row.password,
            "tier": row.tier,
            "enabled": row.enabled,
            "last_used_at": _as_utc(row.last_used_at),
            "last_429_at": _as_utc(row.last_429_at),
            "created_at": _as_utc(row.created_at),
        }

    def add(
        self,
        *,
        provider: str,
        label: str,
        api_key: str,
        tier: str = "free",
        username: str | None = None,
        password: str | None = None,
        enabled: bool = True,
    ) -> int:
        row = ProviderAccountPool(
            provider_name=provider,
            account_label=label,
            api_key=api_key,
            tier=tier,
            username=username,
            password=password,
            enabled=enabled,
        )
        self.session.add(row)
        self.session.commit()
        return row.id

    def get(self, row_id: int) -> dict | None:
        row = self.session.get(ProviderAccountPool, row_id)
        return self._row_to_dict(row) if row else None

    def get_enabled_for(self, provider: str) -> list[dict]:
        rows = (
            self.session.execute(
                select(ProviderAccountPool).where(
                    ProviderAccountPool.provider_name == provider,
                    ProviderAccountPool.enabled.is_(True),
                )
            )
            .scalars()
            .all()
        )
        return [self._row_to_dict(r) for r in rows]

    def get_all_for(self, provider: str) -> list[dict]:
        rows = (
            self.session.execute(
                select(ProviderAccountPool).where(ProviderAccountPool.provider_name == provider)
            )
            .scalars()
            .all()
        )
        return [self._row_to_dict(r) for r in rows]

    def update(self, row_id: int, **fields) -> None:
        allowed = {
            "account_label",
            "api_key",
            "username",
            "password",
            "tier",
            "enabled",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown fields: {sorted(unknown)}")
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        self.session.commit()

    def delete(self, row_id: int) -> None:
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        self.session.delete(row)
        self.session.commit()

    def mark_429(self, row_id: int, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now(UTC)
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        row.last_429_at = now
        self.session.commit()

    def mark_used(self, row_id: int, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now(UTC)
        row = self.session.get(ProviderAccountPool, row_id)
        if row is None:
            return
        row.last_used_at = now
        self.session.commit()
