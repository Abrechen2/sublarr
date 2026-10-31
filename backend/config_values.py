"""How a setting's value is stored in ``config_entries`` and read back.

``config_entries.value`` is text. Saving used ``str(value)`` — a list became
its Python repr — and ``reload_settings`` turned every non-scalar back into a
plain string through ``model_copy``, which skips validation: the protected
languages of the foreign-track cleanup arrived as the string ``"['de','en']"``
and a real remux then dropped the English track (audit #61 A04).

Writes now store collections as JSON. Reads decode by the field's type,
accept the legacy repr and comma forms, and validate the result through the
model so field validators run; a value that still does not fit is dropped
with a warning (the key only, never the value) and the default stays.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import types
import typing
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

_COLLECTIONS = (list, dict, set, tuple)

# GET /config goes to the browser as JSON: a float that is not finite is
# written as "Infinity", which JSON.parse rejects, and an integer past 2**53
# does not survive the round trip.
MAX_SAFE_NUMBER = 2**53


def serialize_config_value(value: Any) -> str:
    """The text a value is stored as: JSON for collections, lower-case booleans."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, _COLLECTIONS):
        return json.dumps(list(value) if isinstance(value, set | tuple) else value)
    return str(value)


def _base_type(annotation: Any) -> Any:
    """``int`` for ``int | None``; the origin (``list``) for ``list[str]``."""
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _base_type(args[0]) if len(args) == 1 else annotation
    return origin or annotation


def decode_config_value(annotation: Any, raw: Any) -> Any:
    """Turn stored text back into the field's type (validation comes after)."""
    base = _base_type(annotation)
    if not isinstance(raw, str):
        if base in (int, float) and not isinstance(raw, bool):
            return _checked_number(raw)
        return raw
    if base is bool:
        return raw.strip().lower() in ("true", "1", "yes", "on")
    if base in (int, float):
        return _checked_number(base(raw.strip()))
    if base in _COLLECTIONS:
        text = raw.strip()
        if not text:
            return base()
        if text[0] in "[{(":
            try:
                return json.loads(text)
            except ValueError:
                # Written by str(list) before JSON: "['de', 'en']".
                return ast.literal_eval(text)
        if base is list:
            # Hand-entered "de, en".
            return [part.strip() for part in text.split(",") if part.strip()]
    return raw.strip() if base is str else raw


def _checked_number(value: Any) -> Any:
    """``value`` unless it is a number the browser cannot hold (ValueError)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        # Compare before any float conversion: float(10**400) overflows.
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("number is not finite")
        if not -MAX_SAFE_NUMBER <= value <= MAX_SAFE_NUMBER:
            raise ValueError("number is out of range")
    return value


def apply_overrides(model: BaseModel, overrides: dict[str, Any]) -> BaseModel:
    """``model`` with ``overrides`` applied, decoded and validated per field.

    Keys the model does not have are ignored (config_entries outlive schema
    changes). A value that cannot be decoded or fails validation keeps the
    model's current value.
    """
    fields = type(model).model_fields
    decoded: dict[str, Any] = {}
    for key, raw in overrides.items():
        if key not in fields:
            continue
        try:
            decoded[key] = decode_config_value(fields[key].annotation, raw)
        except (ValueError, TypeError, SyntaxError):
            logger.warning("Stored setting %s cannot be read; keeping its default", key)
    if not decoded:
        return model

    candidate = {**model.model_dump(), **decoded}
    for key in decoded:
        candidate[key] = decoded[key] = _clamped(fields[key], key, decoded[key])
    for _ in range(len(decoded) + 1):
        try:
            return type(model).model_validate(candidate)
        except ValidationError as exc:
            bad = {str(err["loc"][0]) for err in exc.errors() if err.get("loc")}
            bad &= decoded.keys()
            if not bad:
                logger.warning("Stored settings do not validate; keeping the previous values")
                return model
            for key in bad:
                logger.warning("Stored setting %s is invalid; keeping its default", key)
                candidate[key] = getattr(model, key)
                decoded.pop(key)
    return model


def _clamped(field, key: str, value: Any) -> Any:
    """A stored number outside the field's bounds, moved onto the bound.

    Bounds were enforced on save for one key only, so installs can hold values
    past them; loading those must not silently reset them to the default.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    clamped = value
    for meta in field.metadata:
        if getattr(meta, "ge", None) is not None and clamped < meta.ge:
            clamped = meta.ge
        if getattr(meta, "le", None) is not None and clamped > meta.le:
            clamped = meta.le
    if clamped != value:
        logger.warning("Stored setting %s is out of range; using %s", key, clamped)
    return clamped


def validation_errors(model: BaseModel, updates: dict[str, Any]) -> dict[str, str]:
    """Per key, why ``updates`` would not validate on top of ``model`` (empty: fine)."""
    fields = type(model).model_fields
    decoded: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, raw in updates.items():
        if key not in fields:
            continue
        try:
            decoded[key] = decode_config_value(fields[key].annotation, raw)
        except (ValueError, TypeError, SyntaxError):
            errors[key] = f"Invalid value for {key}"
    if decoded:
        try:
            type(model).model_validate({**model.model_dump(), **decoded})
        except ValidationError as exc:
            for err in exc.errors():
                loc = str(err["loc"][0]) if err.get("loc") else ""
                if loc in decoded:
                    errors.setdefault(loc, f"Invalid value for {loc}: {err.get('msg', 'invalid')}")
    return errors
