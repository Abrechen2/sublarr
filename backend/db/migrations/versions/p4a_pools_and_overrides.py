"""Phase 4a: provider_account_pools + series_settings overrides.

Revision ID: p4a_pools_and_overrides
Revises: b1u2d3g4e5t6
Create Date: 2026-04-17 00:00:00
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "p4a_pools_and_overrides"
down_revision = "b1u2d3g4e5t6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    if not insp.has_table("provider_account_pools"):
        op.create_table(
            "provider_account_pools",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider_name", sa.String(length=50), nullable=False),
            sa.Column("account_label", sa.String(length=100), nullable=False),
            sa.Column("api_key", sa.String(length=500), nullable=False),
            sa.Column("username", sa.String(length=200), nullable=True),
            sa.Column("password", sa.String(length=500), nullable=True),
            sa.Column("tier", sa.String(length=20), nullable=False, server_default="free"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_429_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.UniqueConstraint("provider_name", "account_label", name="uq_pool_provider_label"),
        )
        op.create_index(
            "ix_pool_provider_enabled",
            "provider_account_pools",
            ["provider_name", "enabled"],
        )

    ss_cols = {c["name"] for c in insp.get_columns("series_settings")}
    if "priority_override" not in ss_cols:
        with op.batch_alter_table("series_settings") as batch:
            batch.add_column(sa.Column("priority_override", sa.String(length=20), nullable=True))
    if "min_attempts_per_day" not in ss_cols:
        with op.batch_alter_table("series_settings") as batch:
            batch.add_column(
                sa.Column(
                    "min_attempts_per_day",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )

    # Data backfill: one pool row per configured provider.
    seeded = {
        r[0]
        for r in bind.execute(
            sa.text("SELECT provider_name FROM provider_account_pools")
        ).fetchall()
    }

    # Only providers that authenticate with an API key credential. Others
    # (addic7ed, animetosho, gestdown, kitsunekko, napisy24, subscene, titrari,
    # tvsubtitles) do not need a pool row — they use public / unauthenticated APIs.
    provider_map = [
        (
            "opensubtitles",
            "opensubtitles_api_key",
            "opensubtitles_username",
            "opensubtitles_password",
        ),
        ("subdl", "subdl_api_key", None, None),
        ("jimaku", "jimaku_api_key", None, None),
        (
            "legendasdivx",
            "legendasdivx_api_key",
            "legendasdivx_username",
            "legendasdivx_password",
        ),
        (
            "turkcealtyazi",
            "turkcealtyazi_api_key",
            "turkcealtyazi_username",
            "turkcealtyazi_password",
        ),
    ]
    now = datetime.now(UTC)
    for provider, key_field, user_field, pass_field in provider_map:
        if provider in seeded:
            continue
        api_key = _read_config(bind, key_field)
        if not api_key:
            continue
        username = _read_config(bind, user_field) if user_field else None
        password = _read_config(bind, pass_field) if pass_field else None
        tier_field = f"{provider}_detected_tier"
        tier = _read_config(bind, tier_field) or "free"
        bind.execute(
            sa.text(
                "INSERT INTO provider_account_pools "
                "(provider_name, account_label, api_key, username, password, tier, "
                " enabled, created_at) "
                "VALUES (:p, 'primary', :k, :u, :pw, :t, :enabled, :now)"
            ),
            {
                "p": provider,
                "k": api_key,
                "u": username,
                "pw": password,
                "t": tier,
                "enabled": True,
                "now": now,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    ss_cols = {c["name"] for c in insp.get_columns("series_settings")}
    with op.batch_alter_table("series_settings") as batch:
        if "min_attempts_per_day" in ss_cols:
            batch.drop_column("min_attempts_per_day")
        if "priority_override" in ss_cols:
            batch.drop_column("priority_override")

    if insp.has_table("provider_account_pools"):
        op.drop_index("ix_pool_provider_enabled", table_name="provider_account_pools")
        op.drop_table("provider_account_pools")


def _read_config(bind, key: str) -> str | None:
    row = bind.execute(
        sa.text("SELECT value FROM config_entries WHERE key = :k"), {"k": key}
    ).fetchone()
    if row is None or not row[0]:
        return None
    return str(row[0])
