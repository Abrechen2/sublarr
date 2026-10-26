"""Alembic revision ids must fit PostgreSQL's alembic_version column.

``alembic_version.version_num`` is VARCHAR(32). SQLite ignores the length, so
a longer id passes every SQLite test and only fails on PostgreSQL, where the
upgrade then rolls back and the app keeps running on the old schema
(1.18.0-rc.3: ``sa4_standalone_autoincrement``, 34 characters).
"""

from __future__ import annotations

import ast
from pathlib import Path

_VERSIONS = Path(__file__).resolve().parent.parent / "db" / "migrations" / "versions"
_MAX = 32


def _revision_ids() -> dict[str, str]:
    ids = {}
    for path in sorted(_VERSIONS.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if (
                isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "revision" for t in node.targets)
                and isinstance(node.value, ast.Constant)
            ):
                ids[path.name] = node.value.value
    return ids


def test_every_migration_declares_a_revision():
    assert _revision_ids()


def test_revision_ids_fit_the_postgres_version_column():
    too_long = {name: rev for name, rev in _revision_ids().items() if len(rev) > _MAX}
    assert not too_long, f"revision ids longer than {_MAX} characters: {too_long}"
