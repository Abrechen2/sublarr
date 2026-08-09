"""split the provider success timestamp into search and download

`record_search` and `record_download` both wrote `last_success_at`, so the two
paths were indistinguishable afterwards. That is the exact blind spot behind a
three-day outage: the OpenSubtitles download token expires after 24h while
search keeps working on the API key alone, so searches succeeded, downloads
401'd, and every aggregate stayed green. Separate timestamps make the asymmetry
readable at a glance.

Revision ID: b7c8d9e0f1a2
Revises: c1f2a3b4d5e6
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op

revision = "b7c8d9e0f1a2"
down_revision = "c1f2a3b4d5e6"
branch_labels = None
depends_on = None

_COLUMNS = ("last_search_at", "last_download_at")


def _existing() -> set[str]:
    """Fresh installs build the schema from the models via create_all(), so the
    columns can already exist when this runs."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("provider_stats"):
        return set(_COLUMNS)
    return {c["name"] for c in inspector.get_columns("provider_stats")}


def upgrade():
    present = _existing()
    for name in _COLUMNS:
        if name not in present:
            op.add_column(
                "provider_stats",
                sa.Column(name, sa.DateTime(timezone=True), nullable=True),
            )
    # Deliberately not backfilled from last_success_at. That column cannot say
    # which path produced it, so copying it into both would assert a download
    # succeeded when possibly none ever did — inventing exactly the reassurance
    # this change exists to remove. The fields fill in from the next call.


def downgrade():
    present = _existing()
    for name in _COLUMNS:
        if name in present:
            op.drop_column("provider_stats", name)
