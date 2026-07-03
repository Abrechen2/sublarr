"""Tests for transparent encryption-at-rest in ConfigRepository.

Sensitive keys (per sensitive_keys.is_sensitive_key) must be stored as
``enc:v1:`` ciphertext in the config_entries table, while reads via
get_config_entry / get_all_config_entries must keep returning plaintext.
Non-sensitive keys must remain stored verbatim (no behavior change).
"""

import pytest

import config_crypto
from db.models.core import ConfigEntry
from db.repositories.config import ConfigRepository
from extensions import db


@pytest.fixture
def repo(app_ctx):
    """Create a ConfigRepository instance within app context."""
    return ConfigRepository()


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path, monkeypatch):
    """Isolate the encryption master key per test (same pattern as test_config_crypto.py)."""
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()
    yield
    config_crypto.reset_cipher_cache()


def test_sensitive_value_is_ciphertext_in_db(repo):
    """A sensitive key is encrypted at rest but reads back as plaintext."""
    repo.save_config_entry("opensubtitles_api_key", "SECRET123")

    raw = db.session.get(ConfigEntry, "opensubtitles_api_key").value
    assert raw.startswith("enc:v1:")
    assert "SECRET123" not in raw
    assert repo.get_config_entry("opensubtitles_api_key") == "SECRET123"


def test_non_sensitive_value_stored_plaintext(repo):
    """A non-sensitive key is stored verbatim — no encryption overhead."""
    repo.save_config_entry("wanted_search_interval", "3600")

    raw = db.session.get(ConfigEntry, "wanted_search_interval").value
    assert raw == "3600"
    assert repo.get_config_entry("wanted_search_interval") == "3600"


def test_get_all_decrypts(repo):
    """get_all_config_entries transparently decrypts sensitive values."""
    repo.save_config_entry("subdl_api_key", "abc")
    repo.save_config_entry("wanted_search_interval", "3600")

    all_entries = repo.get_all_config_entries()
    assert all_entries["subdl_api_key"] == "abc"
    assert all_entries["wanted_search_interval"] == "3600"
