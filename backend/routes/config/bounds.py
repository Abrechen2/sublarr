"""Range checks for integer config keys saved through PUT /config.

``reload_settings`` overlays DB overrides with ``model_copy``, which does not
run validation, so a ``Field(ge=, le=)`` on ``UISettings`` only guards values
constructed in code. Keys listed here are checked on save against the bounds
declared on the field itself — the Field stays the single source of the
numbers.

Deliberately an allowlist rather than every constrained field: switching on
enforcement for fields whose bounds were never enforced could reject values
existing installs already store and the UI already sends.
"""

from __future__ import annotations

import types
import typing

BOUNDED_INT_KEYS: frozenset[str] = frozenset({"foreign_track_sweep_budget_s"})


def _field_bounds(key: str) -> tuple[int | None, int | None]:
    from config_settings import UISettings

    ge = le = None
    for meta in UISettings.model_fields[key].metadata:
        ge = getattr(meta, "ge", ge)
        le = getattr(meta, "le", le)
    return ge, le


def coerce_bounded_int(key: str, value: object) -> tuple[int | None, str | None]:
    """Return ``(int_value, None)`` when valid, else ``(None, error_message)``.

    Accepts an int or a decimal string (the settings forms send strings);
    rejects bools, floats, None and anything outside the field's bounds.
    """
    ge, le = _field_bounds(key)
    parsed: int | None = None
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            parsed = None
    elif type(value) is int:
        parsed = value
    in_range = parsed is not None and (ge is None or parsed >= ge) and (le is None or parsed <= le)
    if not in_range:
        return None, f"{key} must be an integer between {ge} and {le}"
    return parsed, None


def literal_choices(key: str) -> set | None:
    """The allowed values of a ``Literal[...]`` setting, else None.

    Derived from the field annotation, so a future Literal setting is checked
    without touching the route. Literal fields were never accepted with any
    other value by the UI (they are selects), so enforcing them rejects
    nothing a real install stores.
    """
    from config_settings import UISettings

    field = UISettings.model_fields.get(key)
    return None if field is None else _choices_of(field.annotation)


def _choices_of(annotation: object) -> set | None:
    """``Literal[...]`` -> its values; ``Literal[...] | None`` (or
    ``Optional[Literal[...]]``) -> its values plus None; anything else -> None."""
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return set(typing.get_args(annotation))
    if origin not in (typing.Union, types.UnionType):
        return None
    members = typing.get_args(annotation)
    literals = [m for m in members if typing.get_origin(m) is typing.Literal]
    rest = [m for m in members if m not in literals]
    if not literals or any(m is not type(None) for m in rest):
        return None
    choices: set = set()
    for member in literals:
        choices.update(typing.get_args(member))
    if rest:
        choices.add(None)
    return choices


def validate_import_value(key: str, value: object) -> tuple[object, str | None]:
    """``(value_to_save, None)`` for a valid imported value of a checked key
    (Literal settings, ``BOUNDED_INT_KEYS``), else ``(None, error_message)``.
    Keys without a check pass through unchanged.

    The import path saves strings and ``reload_settings`` never validates, so
    an invalid value would otherwise surface as a broken settings reload.
    """
    if key in BOUNDED_INT_KEYS:
        return coerce_bounded_int(key, value)
    choices = literal_choices(key)
    if choices is not None and value not in choices:
        return None, f"{key} must be one of {sorted(choices, key=str)}"
    return value, None


def literal_keys() -> frozenset[str]:
    from config_settings import UISettings

    return frozenset(k for k in UISettings.model_fields if literal_choices(k) is not None)
