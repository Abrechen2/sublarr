# B1 — Split `backend/providers/__init__.py` (893 → < 500 LOC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `backend/providers/__init__.py` from 893 LOC to under 500 LOC by extracting provider-class registration, Flask-context singleton helpers, and two cohesive method groups (config resolution + status reporting) from `ProviderManager` into sibling modules and mixins. The public import surface from `providers` stays byte-identical for all 53 callers.

**Architecture:**
- Follow the established mixin pattern (`SearchCoordinatorMixin` in `providers/search_coordinator.py` is already used this way).
- `ProviderManager` grows from inheriting one mixin to three: `SearchCoordinatorMixin`, `ConfigResolvingMixin`, `StatusReportingMixin`. Python's C3 linearisation handles the MRO cleanly because the three mixins define disjoint method sets.
- Provider-class registration state (`_PROVIDER_CLASSES`, `@register_provider`, `_BUILTIN_PROVIDERS`, `_import_builtin_providers`) moves into `providers/registry.py` — already the home of `PROVIDER_METADATA`, the natural extension point.
- Flask-context singleton machinery (`get_provider_manager`, `invalidate_manager`, `update_manager_providers`, the `_get_from_extensions` family) moves to a new `providers/manager_singleton.py`.
- `providers/__init__.py` becomes a thin façade: re-exports from the siblings plus the trimmed `ProviderManager` class body that still contains the core lifecycle (`__init__`, `_load_plugins`, `_init_providers`, `download`, `search_and_download_best`, `save_subtitle`, `get_provider`, `shutdown`, `update_providers`).

**Tech Stack:** Python 3.12, pytest. No new dependencies.

**Cross-cutting framework (per spec §5):**
- Rollback: `git revert` per task — no schema, no data touched.
- Feature flag: N/A — internal refactor with no observable behaviour change.
- Observability metric: `len(open("backend/providers/__init__.py").readlines()) < 500` pinned by a unit test added in Task 6.
- Migration notes: none.
- Docs-with-code: CLAUDE.md verified in Task 6 (likely no change needed — the file still exposes the same public surface).

**Open architectural question (not blocking this plan):** The existing `SearchCoordinatorMixin` in `providers/search_coordinator.py` is 878 LOC — the mixin itself has become a god-file. Adding two more mixins here applies the same pattern, which suggests the pattern does not scale. Composition-based refactoring (holding collaborators as attributes with delegating methods) would break the "no public API change" rule and is a bigger discussion. Documenting the concern in the Inspiration Backlog of the beta-roadmap spec is the right move — out of scope for this plan.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `backend/providers/__init__.py` | modified | Thin façade: re-exports siblings + trimmed `ProviderManager` (orchestration methods only). Target: ≤ 400 LOC. |
| `backend/providers/registry.py` | extended (currently 20 LOC) | `PROVIDER_METADATA` (existing) + `_PROVIDER_CLASSES` + `register_provider()` + `_BUILTIN_PROVIDERS` + `_import_builtin_providers()` (extracted). Target: ~70 LOC. |
| `backend/providers/manager_singleton.py` | **created** | Flask-context helpers + `get_provider_manager()` + `invalidate_manager()` + `update_manager_providers()`. Target: ~100 LOC. |
| `backend/providers/manager_config_mixin.py` | **created** | `ConfigResolvingMixin` class with `_get_provider_config`, `_get_rate_limit`, `_compute_dynamic_timeout`, `_get_timeout`, `_get_retries`, `_check_rate_limit`. Target: ~180 LOC. |
| `backend/providers/manager_status_mixin.py` | **created** | `StatusReportingMixin` class with `get_provider_status`, `get_provider_summary`, `_get_provider_config_fields`. Target: ~200 LOC. |
| `backend/tests/test_providers_init_refactor_safety.py` | **created** | Characterization tests added in Task 1, extended with the LOC guard in Task 6. |

---

## Task 1: Add characterization tests for `providers/__init__.py`

Existing test coverage (do NOT touch these):
- `backend/tests/test_provider_*.py` — many files exercising individual provider adapters and the coordinator's search/retry logic.
- `backend/tests/test_phase1_e2e.py`, `test_phase4a_e2e.py` — end-to-end coordinator flows.

What is NOT yet pinned by existing tests, and what your new test file MUST cover:
1. The 10 public symbols importable from `providers`: `ProviderManager`, `get_provider_manager`, `invalidate_manager`, `update_manager_providers`, `register_provider`, `_PROVIDER_CLASSES`, `_stream_download`, `_validate_subtitle_content`, `compute_score`, `ProviderAuthError` / `ProviderRateLimitError` / `ProviderTimeoutError`.
2. `get_provider_manager()` returns a singleton (idempotent).
3. `invalidate_manager()` resets the singleton so the next `get_provider_manager()` returns a different instance.
4. `update_manager_providers("opensubtitles,jimaku")` updates the provider set on the live singleton without replacing the instance.
5. `register_provider` decorator is idempotent on duplicate class names (logs warning, keeps first registration).
6. `ProviderManager.get_provider_status()` returns a list of dicts with expected keys on each entry.
7. `ProviderManager.get_provider_summary()` returns a dict with expected top-level keys.
8. `ProviderManager.shutdown()` does not raise and leaves the instance in a quiescent state.

**Files:**
- Create: `backend/tests/test_providers_init_refactor_safety.py`

- [ ] **Step 1: Write the characterization test file**

Write ~15 top-level `def test_*():` functions covering the 8 contract points above. Follow the same patterns as `backend/tests/test_config_refactor_safety.py`: plain functions, inline `from providers import ...`, a teardown fixture that calls `invalidate_manager()` after every test to prevent singleton state from leaking across tests.

The implementer must read the current `backend/providers/__init__.py` to discover the exact return shape of `get_provider_status()` and `get_provider_summary()` (pin the actual shape, not an imagined one). If a characterization test fails on the unmodified code, the TEST is wrong — fix the test, do NOT change `providers/__init__.py`.

Include these 15 tests (spelled out as headers; implementer fills the body by reading current behaviour):

```python
def test_provider_manager_class_importable_from_providers(): ...
def test_get_provider_manager_importable(): ...
def test_invalidate_manager_importable(): ...
def test_update_manager_providers_importable(): ...
def test_register_provider_importable(): ...
def test_provider_classes_dict_importable(): ...
def test_stream_download_importable(): ...
def test_validate_subtitle_content_importable(): ...
def test_compute_score_importable(): ...
def test_provider_exceptions_importable(): ...

def test_get_provider_manager_returns_singleton(): ...
def test_invalidate_manager_creates_new_instance_on_next_call(): ...
def test_update_manager_providers_mutates_live_singleton(): ...

def test_get_provider_status_shape(): ...
def test_get_provider_summary_shape(): ...

def test_register_provider_rejects_duplicate_name(): ...  # asserts warning + first wins

def test_shutdown_does_not_raise(): ...
```

Plus the autouse teardown fixture:

```python
@pytest.fixture(autouse=True)
def _reset_provider_manager_after_test():
    yield
    from providers import invalidate_manager
    invalidate_manager()
```

- [ ] **Step 2: Run the new test file alone**

Run: `cd backend && python -m pytest tests/test_providers_init_refactor_safety.py -v`
Expected: all new tests PASS on the unmodified codebase.

- [ ] **Step 3: Run the full provider-related test suite**

Run: `cd backend && python -m pytest tests/test_provider_budget.py tests/test_provider_rate_limit_propagation.py tests/test_phase1_e2e.py tests/test_phase4a_e2e.py tests/test_providers_init_refactor_safety.py -v`
Expected: no new failures.

- [ ] **Step 4: Run ruff on the new test file**

Run: `cd backend && ruff check tests/test_providers_init_refactor_safety.py && ruff format --check tests/test_providers_init_refactor_safety.py`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_providers_init_refactor_safety.py
git commit -m "test(providers): characterization tests pinning manager singleton + status shape (B1/providers prep)"
```

---

## Task 2: Extend `providers/registry.py` with class registration machinery

Move from `providers/__init__.py`:
- `_PROVIDER_CLASSES: dict[str, type[SubtitleProvider]] = {}` (module-level dict, line 46)
- `def register_provider(cls): ...` decorator (lines 52-71)
- `_BUILTIN_PROVIDERS = (...)` class-level tuple inside ProviderManager (lines 195-218) — **PROMOTE to module-level constant** in registry.py
- `_import_builtin_providers()` staticmethod inside ProviderManager (lines 220-229) — **CONVERT to module function** in registry.py

Why promote from class-level to module-level: these are global registration state, not ProviderManager instance state. The staticmethod-inside-class was an encapsulation artefact of having the monolith; once extracted, they sit more naturally at module scope.

**Files:**
- Modify: `backend/providers/registry.py` (currently 20 LOC, will grow to ~70 LOC)
- Modify: `backend/providers/__init__.py` (remove the moved code, add re-exports)

- [ ] **Step 1: Extend `registry.py`**

Open `backend/providers/registry.py`. Append after the existing `PROVIDER_METADATA` dict:

```python
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from providers.base import SubtitleProvider

logger = logging.getLogger(__name__)

# Provider-class registry — populated by @register_provider decorator on import.
_PROVIDER_CLASSES: dict[str, "type[SubtitleProvider]"] = {}


def register_provider(cls: "type[SubtitleProvider]") -> "type[SubtitleProvider]":
    """Decorator to register a provider class.

    Built-in providers always win on name collision: if a name is already
    registered, a warning is logged and the duplicate is skipped.
    """
    if cls.name in _PROVIDER_CLASSES:
        logger.warning(
            "Provider name collision: '%s' already registered by %s, skipping %s",
            cls.name,
            _PROVIDER_CLASSES[cls.name].__name__,
            cls.__name__,
        )
        return cls
    _PROVIDER_CLASSES[cls.name] = cls
    return cls


# Built-in provider module names — imported dynamically to trigger
# @register_provider decorators at the top of each module.
_BUILTIN_PROVIDERS: tuple[str, ...] = (
    "opensubtitles",
    "jimaku",
    "animetosho",
    "subdl",
    "subsdump",
    "gestdown",
    "podnapisi",
    "kitsunekko",
    "napisy24",
    "titrari",
    "legendasdivx",
    "subscene",
    "addic7ed",
    "tvsubtitles",
    "turkcealtyazi",
    "subsource",
    "subf2m",
    "yifysubtitles",
    "zimuku",
    "betaseries",
    "titlovi",
    "embedded",
)


def import_builtin_providers() -> None:
    """Import all built-in provider modules to trigger @register_provider decorators."""
    import importlib

    for name in _BUILTIN_PROVIDERS:
        try:
            importlib.import_module(f"providers.{name}")
        except ImportError as e:
            logger.debug("Provider %s not available: %s", name, e)


__all__ = [
    "PROVIDER_METADATA",
    "_PROVIDER_CLASSES",
    "register_provider",
    "_BUILTIN_PROVIDERS",
    "import_builtin_providers",
]
```

Note the naming change: `_import_builtin_providers` (leading underscore, staticmethod-style) becomes `import_builtin_providers` (module function). The leading underscore was about class-member privacy; at module scope it is now properly internal but not name-mangled. **This is a renaming change; callers of `ProviderManager._import_builtin_providers()` (one caller: `_init_providers`) must be updated to `import_builtin_providers()`** — see Step 2.

- [ ] **Step 2: Remove the moved code from `providers/__init__.py` and update references**

Edit `backend/providers/__init__.py`:

1. Delete the local `_PROVIDER_CLASSES: dict[str, type[SubtitleProvider]] = {}` line (currently line 46).
2. Delete the `register_provider` function definition (currently lines 52-71).
3. Delete the class-level `_BUILTIN_PROVIDERS` tuple inside `ProviderManager` (currently lines 195-218).
4. Delete the `@staticmethod` `_import_builtin_providers` method inside `ProviderManager` (currently lines 220-229).
5. Update the existing import at the top of the file:

```python
# OLD (line 39):
from providers.registry import PROVIDER_METADATA

# NEW:
from providers.registry import (  # noqa: F401 — _PROVIDER_CLASSES, register_provider re-exported
    PROVIDER_METADATA,
    _BUILTIN_PROVIDERS,
    _PROVIDER_CLASSES,
    import_builtin_providers,
    register_provider,
)
```

6. Update the ONE internal caller of the former staticmethod. Inside `ProviderManager._init_providers()` (line 231), find `self._import_builtin_providers()` and replace with `import_builtin_providers()`:

```python
def _init_providers(self):
    """Initialize enabled providers based on config."""
    # Import providers to trigger registration
    import_builtin_providers()   # <-- was: self._import_builtin_providers()
    ...  # rest unchanged
```

- [ ] **Step 3: Run the characterization + full provider tests**

Run: `cd backend && python -m pytest tests/test_providers_init_refactor_safety.py tests/test_provider_budget.py tests/test_provider_rate_limit_propagation.py tests/test_phase1_e2e.py tests/test_phase4a_e2e.py -v`
Expected: all pass.

Key regression to watch: `register_provider` is used as a decorator on all 22 built-in provider modules. If the extraction breaks the decorator, importing any provider module will fail at module load time — the full provider test suite catches this instantly.

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: no new failures.

- [ ] **Step 5: Ruff**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: clean (no new findings beyond pre-existing).

- [ ] **Step 6: Commit**

```bash
git add backend/providers/registry.py backend/providers/__init__.py
git commit -m "refactor(providers): move class registration to registry.py (B1/providers step 1/4)"
```

---

## Task 3: Extract Flask-context singleton to `providers/manager_singleton.py`

Move from `providers/__init__.py`:
- `_provider_manager_lock = threading.Lock()` (line 72)
- `_manager: Optional["ProviderManager"] = None` (line 49)
- `def get_provider_manager()` (lines 73-95)
- `def invalidate_manager()` (lines 97-104)
- `def _has_flask_app_context()` (lines 106-113)
- `def _get_from_extensions(key)` (lines 115-122)
- `def _set_in_extensions(key, value)` (lines 124-131)
- `def _pop_from_extensions(key)` (lines 133-140)
- `def update_manager_providers(new_enabled_str)` (lines 142-156)

All of this is process-level state + helpers — zero dependency on any specific `ProviderManager` instance method. Clean extraction.

**Files:**
- Create: `backend/providers/manager_singleton.py`
- Modify: `backend/providers/__init__.py` (remove moved code, add re-export block)

- [ ] **Step 1: Create `backend/providers/manager_singleton.py`**

The new file imports `ProviderManager` only under `TYPE_CHECKING` + uses a late-binding import inside function bodies for the actual instantiation, to avoid a circular import (`providers/__init__.py` already imports symbols from this new module).

```python
# backend/providers/manager_singleton.py
"""Process-wide singleton accessor for ProviderManager.

Other modules call `get_provider_manager()` to retrieve the active
ProviderManager instance and `invalidate_manager()` to clear it.
`update_manager_providers(...)` mutates the live instance's provider set.

Importing rule: this module MUST NOT import `ProviderManager` at the
module level — that would cause a circular import because
`providers/__init__.py` re-exports symbols from this file. The actual
ProviderManager instantiation happens via a lazy import inside the
function bodies.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from providers import ProviderManager

logger = logging.getLogger(__name__)

_provider_manager_lock = threading.Lock()
_manager: Optional["ProviderManager"] = None


def _has_flask_app_context() -> bool:
    """Check if we are inside an active Flask application context."""
    try:
        from flask import current_app

        _ = current_app._get_current_object()  # noqa: SLF001
        return True
    except Exception:
        return False


def _get_from_extensions(key: str):
    """Read a value from the current Flask app's extensions, or None."""
    from flask import current_app

    return current_app.extensions.get(key)


def _set_in_extensions(key: str, value) -> None:
    """Store a value in the current Flask app's extensions."""
    from flask import current_app

    current_app.extensions[key] = value


def _pop_from_extensions(key: str) -> None:
    """Remove a key from the current Flask app's extensions if present."""
    from flask import current_app

    current_app.extensions.pop(key, None)


def get_provider_manager() -> "ProviderManager":
    """Get or create the singleton ProviderManager (thread-safe).

    When called inside a Flask app context, the result is stored in and
    retrieved from ``app.extensions["provider_manager"]`` — this lets tests
    inject a mock by writing to that key. Falls back to a module-level
    global when no app context is available (e.g. scheduler threads).
    """
    global _manager

    # Lazy import to avoid circular dependency with providers.__init__
    from providers import ProviderManager

    if _has_flask_app_context():
        existing = _get_from_extensions("provider_manager")
        if existing is not None:
            return existing
        with _provider_manager_lock:
            existing = _get_from_extensions("provider_manager")
            if existing is not None:
                return existing
            instance = ProviderManager()
            _set_in_extensions("provider_manager", instance)
            return instance

    if _manager is not None:
        return _manager
    with _provider_manager_lock:
        if _manager is not None:
            return _manager
        _manager = ProviderManager()
        return _manager


def invalidate_manager() -> None:
    """Reset the singleton. Next get_provider_manager() call rebuilds it."""
    global _manager
    with _provider_manager_lock:
        if _has_flask_app_context():
            _pop_from_extensions("provider_manager")
        _manager = None


def update_manager_providers(new_enabled_str: str) -> None:
    """Update the live singleton's provider set in-place.

    Avoids recreating the manager on every config change — preserves
    rate-limit state, circuit breakers, and cache warmth.
    """
    try:
        manager = get_provider_manager()
        manager.update_providers(new_enabled_str)
    except Exception as exc:
        logger.warning("Failed to update provider manager in-place: %s", exc)
        invalidate_manager()


__all__ = [
    "get_provider_manager",
    "invalidate_manager",
    "update_manager_providers",
]
```

**IMPORTANT:** the implementer must read the current `providers/__init__.py` lines 72-156 to confirm the body of each function is copied verbatim (especially the double-checked-locking fragments and the Flask-context fallback order). If the current file has a slightly different `get_provider_manager` (e.g. an extra log line, a different `extensions` key name), copy the current version exactly — do not paraphrase.

- [ ] **Step 2: Remove the moved code from `providers/__init__.py`, add re-export**

Edit `backend/providers/__init__.py`:

1. Delete the lines that are now in the new file:
   - `_provider_manager_lock = threading.Lock()` (currently line 72)
   - `_manager: Optional["ProviderManager"] = None` (currently line 49)
   - `def get_provider_manager()` and body (lines 73-95)
   - `def invalidate_manager()` and body (lines 97-104)
   - `def _has_flask_app_context()` (lines 106-113)
   - `def _get_from_extensions()` (lines 115-122)
   - `def _set_in_extensions()` (lines 124-131)
   - `def _pop_from_extensions()` (lines 133-140)
   - `def update_manager_providers()` (lines 142-156)
2. Drop the now-unused imports: `from typing import Optional` (still needed? check — after removal, if nothing else references `Optional`, drop it; else keep).
3. Add a re-export block immediately after the existing registry re-export:

```python
# Flask-context singleton — re-exported via this module for backwards compatibility.
from providers.manager_singleton import (  # noqa: E402, F401
    get_provider_manager,
    invalidate_manager,
    update_manager_providers,
)
```

`F401` is correct here because after Task 3, `providers/__init__.py` no longer references `get_provider_manager` etc. in its body — they are pure re-exports.

- [ ] **Step 3-6: Same as Task 2** — run targeted tests, full suite, ruff, then commit:

```bash
git add backend/providers/manager_singleton.py backend/providers/__init__.py
git commit -m "refactor(providers): extract Flask-context singleton to manager_singleton.py (B1/providers step 2/4)"
```

---

## Task 4: Extract config-resolving methods to `ConfigResolvingMixin`

Move from `ProviderManager` into a new mixin class:
- `_get_provider_config(self, name)` (lines 392-440)
- `_get_rate_limit(self, provider_name)` (lines 441-452)
- `_compute_dynamic_timeout(self, provider_name, stats)` (lines 453-473)
- `_get_timeout(self, provider_name, all_stats)` (lines 474-501)
- `_get_retries(self, provider_name)` (lines 502-513)
- `_check_rate_limit(self, provider_name)` (lines 514-559)

All six methods read `self.settings`, `self._providers`, `self._rate_limits`, `self._rate_limit_lock`, `self._server_rate_limit_until` — all state that is initialised in `ProviderManager.__init__`. These attributes must exist on the concrete class that inherits the mixin; that is the standard Python mixin contract, and `SearchCoordinatorMixin` already relies on it.

**Files:**
- Create: `backend/providers/manager_config_mixin.py`
- Modify: `backend/providers/__init__.py` (remove the 6 methods, add `ConfigResolvingMixin` to `ProviderManager`'s base list)

- [ ] **Step 1: Create `backend/providers/manager_config_mixin.py`**

Skeleton (verbatim copy from `providers/__init__.py` for each method body):

```python
# backend/providers/manager_config_mixin.py
"""Config / rate-limit / timeout resolution methods for ProviderManager.

Used as a mixin — not instantiated directly. The mixin methods read
instance attributes (self.settings, self._providers, self._rate_limits,
self._rate_limit_lock, self._server_rate_limit_until) that are
initialised by ProviderManager.__init__.

Importing rule: keep all provider-state reads going through `self`; do
NOT import `ProviderManager` here (would cause a circular import).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from providers.registry import PROVIDER_METADATA

if TYPE_CHECKING:
    pass  # No forward refs needed — all state accessed via self

logger = logging.getLogger(__name__)


class ConfigResolvingMixin:
    """Mixin for ProviderManager that owns per-provider config lookup,
    rate-limit tracking, and dynamic timeout computation."""

    # === VERBATIM COPY of _get_provider_config from current providers/__init__.py:392-440 ===
    # === VERBATIM COPY of _get_rate_limit from current providers/__init__.py:441-452 ===
    # === VERBATIM COPY of _compute_dynamic_timeout from current providers/__init__.py:453-473 ===
    # === VERBATIM COPY of _get_timeout from current providers/__init__.py:474-501 ===
    # === VERBATIM COPY of _get_retries from current providers/__init__.py:502-513 ===
    # === VERBATIM COPY of _check_rate_limit from current providers/__init__.py:514-559 ===


__all__ = ["ConfigResolvingMixin"]
```

**IMPORTANT for the implementer:** Open the current `backend/providers/__init__.py` at lines 392-559 and paste each method body VERBATIM in place of the placeholder comments. Preserve all blank lines, docstrings, inline comments. The diff for this task must be a pure move — zero semantic change.

- [ ] **Step 2: Remove the 6 methods from `ProviderManager`, add mixin to inheritance**

Edit `backend/providers/__init__.py`:

1. Delete the 6 method bodies (currently lines 392-559). Be careful not to delete neighbouring methods.
2. Add the mixin to the `ProviderManager` class declaration:

```python
# OLD:
from providers.search_coordinator import SearchCoordinatorMixin

class ProviderManager(SearchCoordinatorMixin):
    ...

# NEW:
from providers.manager_config_mixin import ConfigResolvingMixin
from providers.search_coordinator import SearchCoordinatorMixin

class ProviderManager(SearchCoordinatorMixin, ConfigResolvingMixin):
    ...
```

The order of mixins matters for MRO: put `SearchCoordinatorMixin` first (matches the existing order, preserves method resolution for any accidentally shared attribute). After this task, MRO is:
```
ProviderManager -> SearchCoordinatorMixin -> ConfigResolvingMixin -> object
```
None of the three define overlapping methods, so MRO ordering has no behavioural effect — but keeping `SearchCoordinatorMixin` first is the safe documented position.

- [ ] **Step 3-6: Same as Task 2** — targeted tests, full suite, ruff, commit:

```bash
git add backend/providers/manager_config_mixin.py backend/providers/__init__.py
git commit -m "refactor(providers): extract ConfigResolvingMixin from ProviderManager (B1/providers step 3/4)"
```

---

## Task 5: Extract status-reporting methods to `StatusReportingMixin`

Move from `ProviderManager` into a second mixin:
- `get_provider_status(self)` (lines 632-762)
- `get_provider_summary(self)` (lines 763-812)
- `_get_provider_config_fields(name)` (lines 813-823, currently a `@staticmethod`)

`_get_provider_config_fields` is static (takes no `self`); it is kept as a static method on the mixin so the class can still call it via `cls.` or `self.` (both resolve the same way on a staticmethod).

**Files:**
- Create: `backend/providers/manager_status_mixin.py`
- Modify: `backend/providers/__init__.py` (remove the 3 methods, add `StatusReportingMixin` to `ProviderManager`'s base list)

- [ ] **Step 1: Create `backend/providers/manager_status_mixin.py`**

Skeleton:

```python
# backend/providers/manager_status_mixin.py
"""Status and summary reporting methods for ProviderManager.

Used as a mixin. Reads self._providers, self._rate_limits,
self._server_rate_limit_until, self._circuit_breakers, and self.settings.
Does not mutate state.

Importing rule: do NOT import `ProviderManager` here (would cause a
circular import). Access all state via self.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from providers.registry import PROVIDER_METADATA

logger = logging.getLogger(__name__)


class StatusReportingMixin:
    """Mixin for ProviderManager that owns read-only status/summary APIs."""

    # === VERBATIM COPY of get_provider_status from current providers/__init__.py:632-762 ===
    # === VERBATIM COPY of get_provider_summary from current providers/__init__.py:763-812 ===
    # === VERBATIM COPY of _get_provider_config_fields from current providers/__init__.py:813-823 ===


__all__ = ["StatusReportingMixin"]
```

**IMPORTANT for the implementer:** Open `backend/providers/__init__.py` at lines 632-823 and paste each method body verbatim. `_get_provider_config_fields` is decorated with `@staticmethod` — preserve that decoration.

- [ ] **Step 2: Remove the 3 methods from `ProviderManager`, add mixin**

Edit `backend/providers/__init__.py`:

1. Delete lines 632-823.
2. Update the class declaration:

```python
from providers.manager_config_mixin import ConfigResolvingMixin
from providers.manager_status_mixin import StatusReportingMixin
from providers.search_coordinator import SearchCoordinatorMixin

class ProviderManager(SearchCoordinatorMixin, ConfigResolvingMixin, StatusReportingMixin):
    ...
```

Final MRO:
```
ProviderManager -> SearchCoordinatorMixin -> ConfigResolvingMixin -> StatusReportingMixin -> object
```
No method-name collisions across the three mixins — confirmed by inspecting the method lists extracted in Tasks 4 and 5.

- [ ] **Step 3-6: Same pattern** — tests, ruff, commit:

```bash
git add backend/providers/manager_status_mixin.py backend/providers/__init__.py
git commit -m "refactor(providers): extract StatusReportingMixin from ProviderManager (B1/providers step 4/4)"
```

---

## Task 6: Pin LOC guard, verify CLAUDE.md, frontend smoke

Analogous to Task 5 of the config.py split plan. Pins the `<500 LOC` achievement with a regression guard, audits CLAUDE.md for stale references, and runs the frontend suite as an end-to-end smoke.

**Files:**
- Modify: `backend/tests/test_providers_init_refactor_safety.py` (append the LOC guard test)
- Verify (read-only): `D:/Sublarr_Projekt/Sublarr/CLAUDE.md`, `D:/Sublarr_Projekt/CLAUDE.md`

- [ ] **Step 1: Append the LOC-guard test**

```python
def test_providers_init_py_under_500_loc():
    """Pin B1/providers achievement: providers/__init__.py must stay below 500 LOC.

    If you are adding provider-class registration, put it in providers/registry.py.
    If you are adding singleton / Flask-context code, put it in providers/manager_singleton.py.
    If you are adding config/rate-limit/timeout resolution, put it in providers/manager_config_mixin.py.
    If you are adding status/summary reporting, put it in providers/manager_status_mixin.py.
    providers/__init__.py is intentionally a thin façade + ProviderManager orchestration.
    """
    from pathlib import Path

    path = Path(__file__).parent.parent / "providers" / "__init__.py"
    assert path.exists(), f"providers/__init__.py not found at {path}"
    line_count = sum(1 for _ in path.open(encoding="utf-8"))
    assert line_count < 500, (
        f"backend/providers/__init__.py is {line_count} LOC, must stay below 500. "
        "Move code into the appropriate sibling module (see docstring)."
    )
```

- [ ] **Step 2: Run the guard test**

Run: `cd backend && python -m pytest tests/test_providers_init_refactor_safety.py::test_providers_init_py_under_500_loc -v`
Expected: PASS. Report the actual LOC count — should be in the 350-450 range after Tasks 2-5.

- [ ] **Step 3: Audit CLAUDE.md files**

Read `D:/Sublarr_Projekt/Sublarr/CLAUDE.md` and `D:/Sublarr_Projekt/CLAUDE.md` for stale references to internal structure of `providers/__init__.py`. Likely no edits needed — the public surface (`from providers import get_provider_manager, ProviderManager, ...`) stays identical. If CLAUDE.md specifically mentions "ProviderManager in providers/__init__.py handles X", update to reflect the new split only if it mentions an internal that has moved (e.g. "the staticmethod `_import_builtin_providers`" → now `providers.registry.import_builtin_providers`).

- [ ] **Step 4: Frontend smoke**

Run: `cd frontend && npm run test -- --run`
Expected: 824/824 passed (same as after Task 1 baseline).

- [ ] **Step 5: Final full backend test + ruff**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance && ruff check . && ruff format --check .`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_providers_init_refactor_safety.py
# Conditionally include CLAUDE.md if Step 3 made edits:
git add -u D:/Sublarr_Projekt/Sublarr/CLAUDE.md D:/Sublarr_Projekt/CLAUDE.md 2>/dev/null || true
git commit -m "test(providers): pin providers/__init__.py <500 LOC + verify docs (B1/providers complete)"
```

---

## Acceptance criteria

After all 6 tasks:

- `backend/providers/__init__.py` ≤ 500 LOC (target: ~400).
- `backend/providers/manager_singleton.py`, `backend/providers/manager_config_mixin.py`, `backend/providers/manager_status_mixin.py` exist.
- `backend/providers/registry.py` extended with class registration machinery.
- Public import surface from `providers` is unchanged: `ProviderManager`, `get_provider_manager`, `invalidate_manager`, `update_manager_providers`, `register_provider`, `_PROVIDER_CLASSES`, `_stream_download`, `_validate_subtitle_content`, `compute_score`, `ProviderAuthError`, `ProviderRateLimitError`, `ProviderTimeoutError` — all importable from `providers`.
- `backend/tests/test_providers_init_refactor_safety.py` exists with ≥ 18 tests (17 characterization + 1 LOC guard), all passing.
- `cd backend && python -m pytest --tb=short -q --ignore=tests/performance` reports the same pass count as before this plan plus the new safety tests.
- `cd backend && ruff check . && ruff format --check .` reports no new findings.
- `cd frontend && npm run test -- --run` is green.

---

## Out of scope (explicit)

- `backend/providers/search_coordinator.py` (878 LOC) — gets its own plan in a later cycle.
- The "mixin scaling" architectural concern (SearchCoordinatorMixin alone is 878 LOC) — documented in the beta-roadmap spec's Inspiration Backlog as I7 "Replace mixin pattern with composition for ProviderManager collaborators". Revisit when the second mixin grows past 400 LOC.
- Changing the `ProviderManager` public API — blocked by the "byte-identical public surface" rule.
- Moving `_init_providers` (161 LOC) elsewhere — stays in `ProviderManager` because it owns the instance lifecycle and all registered siblings depend on it.
