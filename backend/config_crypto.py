"""Fernet encryption-at-rest for sensitive config values.

The master key lives in a file OUTSIDE the database
(``{config_dir}/.encryption_key``, ``0600``) so a DB dump alone cannot decrypt.
Ciphertext is version-prefixed (``enc:v1:<token>``) so plaintext and ciphertext
coexist during rollout and ``decrypt()`` is a no-op on plaintext.

The config directory is read from ``SUBLARR_CONFIG_DIR`` (the existing
``config_dir`` BootSettings field, default ``/config``) — no new env var.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_PREFIX = "enc:v1:"
_KEY_FILENAME = ".encryption_key"
_cipher: Fernet | None = None


def _key_path() -> str:
    config_dir = os.environ.get("SUBLARR_CONFIG_DIR", "/config")
    return os.path.join(config_dir, _KEY_FILENAME)


def _load_or_create_key() -> bytes:
    path = _key_path()
    try:
        with open(path, "rb") as fh:
            data = fh.read().strip()
        if data:
            return data
    except FileNotFoundError:
        pass

    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Lost a race with another worker — read what it wrote.
        with open(path, "rb") as fh:
            return fh.read().strip()
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    logger.info("Encryption master key generated at %s", path)
    return key


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        _cipher = Fernet(_load_or_create_key())
    return _cipher


def reset_cipher_cache() -> None:
    """Drop the cached cipher (tests / key rotation)."""
    global _cipher
    _cipher = None


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt(value: str | None) -> str | None:
    if value is None or value == "" or is_encrypted(value):
        return value
    token = _get_cipher().encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt(value: str | None) -> str | None:
    if not is_encrypted(value):
        return value
    token = value[len(_PREFIX) :]
    try:
        return _get_cipher().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt a config value — wrong or missing master key")
        raise
