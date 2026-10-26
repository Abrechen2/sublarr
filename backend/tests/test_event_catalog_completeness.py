"""Every event name passed to emit_event must exist in EVENT_CATALOG.

emit_event drops unknown names with a warning, so a missing entry silently
means the event never reaches the WebSocket bridge, hooks or webhooks.
"""

import ast
from pathlib import Path

from events.catalog import EVENT_CATALOG

BACKEND = Path(__file__).resolve().parent.parent
_SKIP_DIRS = {"tests", ".venv", "venv", "node_modules", "__pycache__"}


def _emitted_event_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for path in BACKEND.rglob("*.py"):
        if _SKIP_DIRS & set(path.relative_to(BACKEND).parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            fname = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            first = node.args[0]
            if (
                fname == "emit_event"
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
            ):
                names.setdefault(first.value, f"{path.relative_to(BACKEND)}:{node.lineno}")
    return names


# Known gaps, older than this test and out of its fix's scope. Drop a name
# here once it is catalogued; the second test fails while a listed name is
# already in the catalog, so the list cannot go stale.
_KNOWN_UNCATALOGUED = frozenset(
    {"batch_process_progress", "batch_process_completed", "wanted_search_failed"}
)


def test_every_emitted_event_is_in_the_catalog():
    emitted = _emitted_event_names()
    assert "subtitle_health_complete" in emitted  # the scanner itself works
    missing = {
        name: where
        for name, where in emitted.items()
        if name not in EVENT_CATALOG and name not in _KNOWN_UNCATALOGUED
    }
    assert not missing, f"emit_event names missing from EVENT_CATALOG: {missing}"


def test_known_gaps_are_still_gaps():
    assert not (_KNOWN_UNCATALOGUED & set(EVENT_CATALOG))


def test_catalog_entries_have_the_common_shape():
    for name, entry in EVENT_CATALOG.items():
        assert {"signal", "label", "description", "payload_keys"} <= set(entry), name
        assert entry["signal"].name == name, name
