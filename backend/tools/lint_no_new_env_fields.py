"""AST linter — enforce the UI-first env-var convention (V1, since 0.88.0-beta).

Sublarr's contract since 0.88.0-beta:

* ``BootSettings`` (a ``pydantic_settings.BaseSettings``) is the ONLY
  class allowed to load values from the environment via
  ``SUBLARR_<field>``. Its membership is curated by the
  ``_ALLOWED_BOOT_FIELDS`` frozenset in ``config_settings.py``.
* All other configuration lives on ``UISettings`` (a ``pydantic.BaseModel``,
  intentionally NOT ``BaseSettings``) and is set through the UI.

This linter walks ``backend/config_settings.py`` and asserts:

1. ``_ALLOWED_BOOT_FIELDS`` is the source of truth.
2. ``BootSettings`` declares EXACTLY the fields in the allowlist —
   no more, no less.
3. ``UISettings`` does not subclass ``BaseSettings`` (subclassing it
   would silently re-introduce env loading).
4. No other class in ``config_settings.py`` subclasses ``BaseSettings``
   except ``BootSettings`` itself.

Exit code 1 on any violation, 0 otherwise. Designed for CI.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config_settings.py"


def _frozenset_members(node: ast.AST) -> set[str] | None:
    """Return the string members of a ``frozenset({...})`` literal, or None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Set)
    ):
        members: set[str] = set()
        for elt in node.args[0].elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                members.add(elt.value)
            else:
                return None
        return members
    return None


def _class_field_names(cls: ast.ClassDef) -> set[str]:
    """Return the names of every annotated assignment at class top-level."""
    fields: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            fields.add(stmt.target.id)
    return fields


def _base_names(cls: ast.ClassDef) -> set[str]:
    """Return the names of all bases used by ``cls``."""
    names: set[str] = set()
    for base in cls.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def lint(path: Path = CONFIG_FILE) -> list[str]:
    """Return a list of violation messages — empty list = clean."""
    if not path.exists():
        return [f"{path} not found"]

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    allowlist: set[str] | None = None
    classes: dict[str, ast.ClassDef] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_ALLOWED_BOOT_FIELDS":
                    allowlist = _frozenset_members(node.value)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_ALLOWED_BOOT_FIELDS"
            and node.value is not None
        ):
            allowlist = _frozenset_members(node.value)
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = node

    violations: list[str] = []

    if allowlist is None:
        violations.append(
            "_ALLOWED_BOOT_FIELDS frozenset literal not found at module top-level "
            "of config_settings.py — UI-first convention cannot be enforced."
        )
        return violations

    boot = classes.get("BootSettings")
    if boot is None:
        violations.append("BootSettings class not found in config_settings.py")
    else:
        boot_fields = _class_field_names(boot)
        extra = boot_fields - allowlist
        missing = allowlist - boot_fields
        if extra:
            violations.append(
                "BootSettings declares fields NOT in _ALLOWED_BOOT_FIELDS: "
                f"{sorted(extra)}. New env-loadable fields are forbidden — "
                "put the field on UISettings instead."
            )
        if missing:
            violations.append(
                "BootSettings is missing fields listed in _ALLOWED_BOOT_FIELDS: "
                f"{sorted(missing)}. Allowlist and class must agree."
            )

    ui = classes.get("UISettings")
    if ui is None:
        violations.append("UISettings class not found in config_settings.py")
    else:
        ui_bases = _base_names(ui)
        if "BaseSettings" in ui_bases:
            violations.append(
                "UISettings must NOT subclass BaseSettings — that would re-enable "
                "env loading for UI fields. Use BaseModel."
            )

    for name, cls in classes.items():
        if name in {"BootSettings", "UISettings", "Settings"}:
            continue
        if "BaseSettings" in _base_names(cls):
            violations.append(
                f"Class {name!r} subclasses BaseSettings — only BootSettings is "
                "allowed to load env vars. Use BaseModel."
            )

    return violations


def main(argv: list[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else CONFIG_FILE
    violations = lint(target)
    if not violations:
        print(f"no-new-env-fields linter: clean ({target})")
        return 0
    print(f"no-new-env-fields linter: {len(violations)} violation(s) in {target}:")
    for msg in violations:
        print(f"  - {msg}")
    print()
    print("UI-first convention (since v0.88.0-beta): only the fields in")
    print("_ALLOWED_BOOT_FIELDS are env-loadable. Everything else is UI-only.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
