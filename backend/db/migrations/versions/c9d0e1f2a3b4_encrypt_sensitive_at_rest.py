"""Encrypt sensitive config values + provider-account-pool credentials at rest

This is a DATA migration (no schema change): it back-fills every already
existing sensitive ``config_entries.value`` and every
``provider_account_pools.api_key`` / ``.password`` with Fernet ciphertext
(``enc:v1:`` prefix), using the same ``config_crypto`` primitives that
``ConfigRepository`` / ``ProviderAccountPoolRepository`` already use for new
writes (Tasks 3-5). ``encrypt`` / ``decrypt`` are idempotent — re-running
``upgrade()`` (or booting a container that already ran it) is a safe no-op.

Revision ID: c9d0e1f2a3b4
Revises: a1b2c3d4e5f7
Create Date: 2026-07-03
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def _encrypt_all(bind):
    """Encrypt every sensitive config_entries value + pool credential in place."""
    from config_crypto import encrypt, is_encrypted
    from sensitive_keys import is_sensitive_key

    for key, value in bind.execute(sa.text("SELECT key, value FROM config_entries")).fetchall():
        if value and is_sensitive_key(key) and not is_encrypted(value):
            bind.execute(
                sa.text("UPDATE config_entries SET value = :v WHERE key = :k"),
                {"v": encrypt(value), "k": key},
            )

    for row_id, api_key, password in bind.execute(
        sa.text("SELECT id, api_key, password FROM provider_account_pools")
    ).fetchall():
        updates = {}
        if api_key and not is_encrypted(api_key):
            updates["api_key"] = encrypt(api_key)
        if password and not is_encrypted(password):
            updates["password"] = encrypt(password)
        if updates:
            set_clause = ", ".join(f"{col} = :{col}" for col in updates)
            updates["row_id"] = row_id
            bind.execute(
                sa.text(f"UPDATE provider_account_pools SET {set_clause} WHERE id = :row_id"),
                updates,
            )


def _decrypt_all(bind):
    """Reverse of ``_encrypt_all`` — restores plaintext (used by downgrade())."""
    from config_crypto import decrypt, is_encrypted
    from sensitive_keys import is_sensitive_key

    for key, value in bind.execute(sa.text("SELECT key, value FROM config_entries")).fetchall():
        if is_encrypted(value) and is_sensitive_key(key):
            bind.execute(
                sa.text("UPDATE config_entries SET value = :v WHERE key = :k"),
                {"v": decrypt(value), "k": key},
            )

    for row_id, api_key, password in bind.execute(
        sa.text("SELECT id, api_key, password FROM provider_account_pools")
    ).fetchall():
        updates = {}
        if is_encrypted(api_key):
            updates["api_key"] = decrypt(api_key)
        if is_encrypted(password):
            updates["password"] = decrypt(password)
        if updates:
            set_clause = ", ".join(f"{col} = :{col}" for col in updates)
            updates["row_id"] = row_id
            bind.execute(
                sa.text(f"UPDATE provider_account_pools SET {set_clause} WHERE id = :row_id"),
                updates,
            )


def upgrade():
    _encrypt_all(op.get_bind())


def downgrade():
    _decrypt_all(op.get_bind())
