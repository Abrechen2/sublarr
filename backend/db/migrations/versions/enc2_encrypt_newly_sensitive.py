"""Encrypt config values whose keys became sensitive after c9d0e1f2a3b4

``sensitive_keys.SENSITIVE_SUFFIXES`` gained ``_apikey`` and ``_pin`` (#61
review, 2026-10-31): ``tvdb_pin`` was masked by the API but stored in plain
text. New writes are encrypted by ``ConfigRepository``; this back-fills rows
saved before. ``encrypt``/``decrypt`` are idempotent and ``decrypt`` passes
plain text through, so a re-run or a downgrade-then-upgrade is safe.

Revision ID: enc2_newly_sensitive
Revises: sa4_standalone_autoincrement
Create Date: 2026-10-31
"""

import sqlalchemy as sa
from alembic import op

revision = "enc2_newly_sensitive"
down_revision = "sa4_standalone_autoincrement"
branch_labels = None
depends_on = None


def upgrade():
    from config_crypto import encrypt, is_encrypted
    from sensitive_keys import is_sensitive_key

    bind = op.get_bind()
    for key, value in bind.execute(sa.text("SELECT key, value FROM config_entries")).fetchall():
        if value and is_sensitive_key(key) and not is_encrypted(value):
            bind.execute(
                sa.text("UPDATE config_entries SET value = :v WHERE key = :k"),
                {"v": encrypt(value), "k": key},
            )


def downgrade():
    # Encrypted values stay readable: ConfigRepository decrypts on read.
    pass
