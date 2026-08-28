"""Which flat config keys the config endpoints are allowed to write.

Both endpoints used to derive this from ``Settings.model_fields``. ``Settings``
is a plain composite class with no ``model_fields``, so the guarded expression
fell through to ``set()`` on every call — and the two callers then failed in
opposite directions from that one empty set: ``/config/import`` is fail-closed
and answered 500 to every request, while ``/config`` reads ``if not valid_keys
or ...`` and therefore validated nothing at all.

The models alone are not the answer either. On the reference install 15 of 73
stored keys are not settings fields — ``ui_password_hash``,
``translation_quality_threshold``, ``usage_stats_consent``, the
``cleanup_*_seeded`` markers and the dotted backend keys. Validating against
the models would have stopped the UI from saving them, turning a missing check
into a visible outage. So a key that is already in ``config_entries`` counts as
writable as well: the application itself put it there.
"""

from __future__ import annotations


def model_config_keys() -> set[str]:
    """Field names declared on the two real settings models."""
    from config_settings import BootSettings, UISettings

    return set(BootSettings.model_fields) | set(UISettings.model_fields)


def writable_config_keys() -> set[str]:
    """Model fields plus every key already stored in ``config_entries``.

    Reading the stored keys keeps this from drifting the way a hand-written
    list would: a key the application writes today is writable tomorrow
    without anyone remembering to extend a literal. A database that cannot be
    read falls back to the model fields, which is still a real set — never the
    empty one that caused the two failures above.
    """
    keys = model_config_keys()
    try:
        from db.config import get_all_config_entries

        keys |= set(get_all_config_entries() or {})
    except Exception:  # noqa: BLE001 — a missing DB must not empty the set
        pass
    # Reading the stored keys is what makes the auth credentials a live
    # concern rather than a theoretical one: on any install where a UI
    # password has been set, ui_password_hash IS in config_entries and would
    # otherwise become writable through the generic endpoint — a second way to
    # set a password that skips "prove you know the current one".
    from ui_auth import AUTH_OWNED_CONFIG_KEYS

    return keys - AUTH_OWNED_CONFIG_KEYS


def is_writable_config_key(key: str) -> bool:
    """Dotted extension keys are always allowed; flat keys must be known.

    The auth-owned keys are refused on both paths — a dotted spelling must not
    become a way around them either.
    """
    from ui_auth import AUTH_OWNED_CONFIG_KEYS

    if key in AUTH_OWNED_CONFIG_KEYS:
        return False
    if "." in key:
        return True
    return key in writable_config_keys()
