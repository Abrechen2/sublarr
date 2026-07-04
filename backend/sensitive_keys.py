"""Classify which config keys / credential fields hold secrets that must be
encrypted at rest.

A key is sensitive when it ends with one of ``SENSITIVE_SUFFIXES`` or equals a
member of ``SENSITIVE_EXACT`` — UNLESS it is in ``EXCLUDED_KEYS`` or namespaced
(contains a ``.``).

Excluded:
- ``ui_session_secret``: the Flask ``SECRET_KEY`` source, stored inside the DB.
  Encrypting it would co-locate key and ciphertext and create a circular
  dependency (the encryption key must live outside the DB).
- ``ui_password_hash``: already a bcrypt hash, not reversible plaintext.

Namespaced (dotted) keys — e.g. ``plugin.<provider>.<field>`` or
``post_processing.<...>`` — are always treated as non-sensitive here, even if
their leaf segment matches a sensitive suffix. These keys are owned by
sub-repositories (``PluginRepository`` in ``db/repositories/plugins.py``,
``post_processing/config_store.py``) that read/write ``config_entries.value``
directly via raw ORM queries and never go through the encrypt/decrypt layer
(``ConfigRepository`` / ``config_crypto``). If the classifier marked a dotted
key sensitive, the back-fill migration would encrypt it, but the bypass
repository would then read back ``enc:v1:`` ciphertext as if it were the
plaintext value — a silent auth failure. Only flat, non-dotted top-level keys
(``opensubtitles_api_key``, ``api_key``, ``github_token``, ...) are the actual
encryption targets.
"""

SENSITIVE_SUFFIXES: tuple[str, ...] = ("_api_key", "_password", "_token", "_secret")
SENSITIVE_EXACT: frozenset[str] = frozenset({"api_key"})
EXCLUDED_KEYS: frozenset[str] = frozenset({"ui_session_secret", "ui_password_hash"})


def is_sensitive_key(key: str) -> bool:
    if "." in key:
        # Namespaced keys belong to sub-repositories that manage their own
        # storage and bypass the encrypt/decrypt layer — see module docstring.
        return False
    if key in EXCLUDED_KEYS:
        return False
    if key in SENSITIVE_EXACT:
        return True
    return key.endswith(SENSITIVE_SUFFIXES)
