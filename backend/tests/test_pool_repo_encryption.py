"""Encryption-at-rest tests for ``ProviderAccountPoolRepository`` (Task 5).

Verifies ``api_key``/``password`` are encrypted before hitting the DB and
transparently decrypted on read, using the same isolated-key pattern as
``test_config_crypto.py``.
"""

from __future__ import annotations

import config_crypto
from db.models.core import ProviderAccountPool
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from extensions import db


def test_pool_api_key_encrypted_in_db(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    repo = ProviderAccountPoolRepository()
    row_id = repo.add(provider="opensubtitles", label="acct1", api_key="KEY99", password="PW88")

    raw = db.session.get(ProviderAccountPool, row_id)
    assert raw.api_key.startswith("enc:v1:")
    assert raw.password.startswith("enc:v1:")
    assert "KEY99" not in raw.api_key
    assert "PW88" not in raw.password

    got = repo.get(row_id)
    assert got["api_key"] == "KEY99"
    assert got["password"] == "PW88"


def test_pool_update_re_encrypts(app_ctx, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    repo = ProviderAccountPoolRepository()
    row_id = repo.add(provider="subdl", label="a", api_key="OLD")
    repo.update(row_id, api_key="NEW")

    raw = db.session.get(ProviderAccountPool, row_id)
    assert raw.api_key.startswith("enc:v1:")
    assert "NEW" not in raw.api_key

    assert repo.get(row_id)["api_key"] == "NEW"
