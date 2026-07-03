"""Tests for the encrypt-sensitive-at-rest Alembic data migration.

Exercises ``_encrypt_all`` / ``_decrypt_all`` directly against a real DB
connection (the ``app_ctx`` fixture, same as the rest of the DB-layer test
suite), instead of monkeypatching ``alembic.op``. This keeps the migration's
actual logic under test without pulling in Alembic's runtime machinery, while
still importing the migration module by its real generated dotted path.

Mirrors the isolated-key pattern used by ``test_config_repo_encryption.py`` /
``test_pool_repo_encryption.py`` (Tasks 3-5).
"""

from __future__ import annotations

import importlib

import sqlalchemy as sa

import config_crypto
from extensions import db


def _migration():
    return importlib.import_module("db.migrations.versions.c9d0e1f2a3b4_encrypt_sensitive_at_rest")


def test_encrypt_all_encrypts_existing_config_secret(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO config_entries (key, value, updated_at) "
            "VALUES ('subdl_api_key', 'PLAIN', :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    _migration()._encrypt_all(conn)

    stored = conn.execute(
        sa.text("SELECT value FROM config_entries WHERE key = 'subdl_api_key'")
    ).scalar_one()
    assert stored.startswith("enc:v1:")
    assert config_crypto.decrypt(stored) == "PLAIN"


def test_encrypt_all_leaves_non_sensitive_untouched(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO config_entries (key, value, updated_at) "
            "VALUES ('wanted_search_interval', '3600', :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    _migration()._encrypt_all(conn)

    stored = conn.execute(
        sa.text("SELECT value FROM config_entries WHERE key = 'wanted_search_interval'")
    ).scalar_one()
    assert stored == "3600"


def test_encrypt_all_is_idempotent(app_ctx, tmp_path, monkeypatch):
    """Running the backfill twice must not double-encrypt (safe to re-run)."""
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO config_entries (key, value, updated_at) "
            "VALUES ('subdl_api_key', 'PLAIN', :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    migration = _migration()
    migration._encrypt_all(conn)
    once = conn.execute(
        sa.text("SELECT value FROM config_entries WHERE key = 'subdl_api_key'")
    ).scalar_one()

    migration._encrypt_all(conn)
    twice = conn.execute(
        sa.text("SELECT value FROM config_entries WHERE key = 'subdl_api_key'")
    ).scalar_one()

    assert once == twice
    assert config_crypto.decrypt(twice) == "PLAIN"


def test_encrypt_all_encrypts_provider_account_pool_credentials(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO provider_account_pools "
            "(provider_name, account_label, api_key, password, tier, enabled, created_at) "
            "VALUES ('opensubtitles', 'acct1', 'KEY99', 'PW88', 'free', 1, :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    _migration()._encrypt_all(conn)

    row = (
        conn.execute(
            sa.text(
                "SELECT api_key, password FROM provider_account_pools WHERE account_label = 'acct1'"
            )
        )
        .mappings()
        .one()
    )
    assert row["api_key"].startswith("enc:v1:")
    assert row["password"].startswith("enc:v1:")
    assert config_crypto.decrypt(row["api_key"]) == "KEY99"
    assert config_crypto.decrypt(row["password"]) == "PW88"


def test_encrypt_all_leaves_pool_row_without_password_untouched(app_ctx, tmp_path, monkeypatch):
    """A pool row with a NULL password must not raise or be modified."""
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO provider_account_pools "
            "(provider_name, account_label, api_key, password, tier, enabled, created_at) "
            "VALUES ('subdl', 'acct2', 'KEY77', NULL, 'free', 1, :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    _migration()._encrypt_all(conn)

    row = (
        conn.execute(
            sa.text(
                "SELECT api_key, password FROM provider_account_pools WHERE account_label = 'acct2'"
            )
        )
        .mappings()
        .one()
    )
    assert row["api_key"].startswith("enc:v1:")
    assert row["password"] is None


def test_decrypt_all_restores_plaintext(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO config_entries (key, value, updated_at) "
            "VALUES ('subdl_api_key', 'PLAIN', :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    migration = _migration()
    migration._encrypt_all(conn)
    migration._decrypt_all(conn)

    stored = conn.execute(
        sa.text("SELECT value FROM config_entries WHERE key = 'subdl_api_key'")
    ).scalar_one()
    assert stored == "PLAIN"


def test_decrypt_all_restores_provider_account_pool_credentials(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    conn = db.session.connection()
    conn.execute(
        sa.text(
            "INSERT INTO provider_account_pools "
            "(provider_name, account_label, api_key, password, tier, enabled, created_at) "
            "VALUES ('opensubtitles', 'acct3', 'KEY55', 'PW44', 'free', 1, :ts)"
        ),
        {"ts": "2026-07-03T00:00:00+00:00"},
    )

    migration = _migration()
    migration._encrypt_all(conn)
    migration._decrypt_all(conn)

    row = (
        conn.execute(
            sa.text(
                "SELECT api_key, password FROM provider_account_pools WHERE account_label = 'acct3'"
            )
        )
        .mappings()
        .one()
    )
    assert row["api_key"] == "KEY55"
    assert row["password"] == "PW44"
