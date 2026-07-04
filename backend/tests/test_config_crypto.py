import os

import pytest

import config_crypto


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()
    yield
    config_crypto.reset_cipher_cache()


def test_round_trip():
    token = config_crypto.encrypt("super-secret-key")
    assert token.startswith("enc:v1:")
    assert config_crypto.decrypt(token) == "super-secret-key"


def test_decrypt_is_noop_on_plaintext():
    assert config_crypto.decrypt("plain-value") == "plain-value"


def test_encrypt_is_idempotent():
    once = config_crypto.encrypt("x")
    twice = config_crypto.encrypt(once)
    assert once == twice
    assert config_crypto.decrypt(twice) == "x"


def test_empty_and_none_pass_through():
    assert config_crypto.encrypt("") == ""
    assert config_crypto.encrypt(None) is None
    assert config_crypto.decrypt("") == ""
    assert config_crypto.decrypt(None) is None


def test_key_file_created_with_owner_only_perms(tmp_path):
    config_crypto.encrypt("trigger-key-creation")
    key_file = tmp_path / ".encryption_key"
    assert key_file.exists()
    if os.name == "posix":
        assert (key_file.stat().st_mode & 0o777) == 0o600


def test_key_persists_across_cipher_reset():
    token = config_crypto.encrypt("persist-me")
    config_crypto.reset_cipher_cache()  # simulates a process restart
    assert config_crypto.decrypt(token) == "persist-me"
