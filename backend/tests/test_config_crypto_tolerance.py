"""decrypt() must tolerate an undecryptable value (wrong/missing master key) by
returning None instead of raising — a DB restored or cloned without its
{config_dir}/.encryption_key must NOT brick the app on boot (get_all_config_entries
runs inside create_app). Regression for the RC-clone boot crash found 2026-07-09.
"""

from cryptography.fernet import Fernet

import config_crypto


def test_decrypt_returns_none_on_wrong_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()

    ciphertext = config_crypto.encrypt("secret-value")  # encrypted under key A
    assert config_crypto.is_encrypted(ciphertext)

    (tmp_path / ".encryption_key").write_bytes(Fernet.generate_key())  # swap to key B
    config_crypto.reset_cipher_cache()

    # Wrong key: must degrade to None, never raise.
    assert config_crypto.decrypt(ciphertext) is None


def test_decrypt_passthrough_plaintext_and_none(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()
    assert config_crypto.decrypt("plain") == "plain"
    assert config_crypto.decrypt(None) is None


def test_encrypt_decrypt_roundtrip_same_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(tmp_path))
    config_crypto.reset_cipher_cache()
    assert config_crypto.decrypt(config_crypto.encrypt("hello")) == "hello"
