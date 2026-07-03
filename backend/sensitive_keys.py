"""Classify which config keys / credential fields hold secrets that must be
encrypted at rest.

A key is sensitive when it ends with one of ``SENSITIVE_SUFFIXES`` or equals a
member of ``SENSITIVE_EXACT`` — UNLESS it is in ``EXCLUDED_KEYS``.

Excluded:
- ``ui_session_secret``: the Flask ``SECRET_KEY`` source, stored inside the DB.
  Encrypting it would co-locate key and ciphertext and create a circular
  dependency (the encryption key must live outside the DB).
- ``ui_password_hash``: already a bcrypt hash, not reversible plaintext.
"""

SENSITIVE_SUFFIXES: tuple[str, ...] = ("_api_key", "_password", "_token", "_secret")
SENSITIVE_EXACT: frozenset[str] = frozenset({"api_key"})
EXCLUDED_KEYS: frozenset[str] = frozenset({"ui_session_secret", "ui_password_hash"})


def is_sensitive_key(key: str) -> bool:
    if key in EXCLUDED_KEYS:
        return False
    if key in SENSITIVE_EXACT:
        return True
    return key.endswith(SENSITIVE_SUFFIXES)
