# B1 — Split `backend/config.py` (846 → < 600 LOC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce `backend/config.py` from 846 LOC to under 600 LOC by extracting the `_SettingsView` family, the `Settings` class, and the singleton management into dedicated sibling modules. Zero behaviour change. The public import surface from `config.py` stays byte-identical for callers.

**Architecture:** `config.py` becomes a thin façade that re-exports from three new sibling modules:
- `backend/config_views.py` — `_SettingsView` base + 5 view subclasses (`GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings`).
- `backend/config_settings.py` — the `Settings` Pydantic model with its 8 instance methods + the 5 grouped-view property accessors.
- `backend/config_singleton.py` — `get_settings()`, `reload_settings()`, the module-level `_settings` cache and lock.

After the split, `config.py` consists of: module docstring + the union of `from X import Y` re-exports for `Settings`, the 5 view classes, `get_settings`, `reload_settings`, plus the existing re-exports for `config_instances`, `config_language_data`, `config_utils`. Order of extraction (Views → Settings → Singleton) is dictated by dependency direction: `Settings` references the views; `get_settings`/`reload_settings` reference `Settings`.

**Tech Stack:** Python 3.12, Pydantic v2 (`pydantic-settings`), pytest. No new dependencies.

**Cross-cutting framework (per spec §5):**
- Rollback: `git revert` per task — no schema or data is touched.
- Feature flag: N/A — internal refactor with no observable behaviour change.
- Observability metric: `len(open("backend/config.py").readlines())` ≤ 600, pinned by a unit test added in Task 5.
- Migration notes: none (no DB or config-entry change).
- Docs-with-code: `CLAUDE.md` is verified to contain no stale references to internal `config.py` structure in Task 5.

---

## File structure

| File | Status | Responsibility |
|---|---|---|
| `backend/config.py` | modified | Public façade. Re-exports symbols from the three new modules and the existing `config_instances`/`config_language_data`/`config_utils`. Final size: ~50 LOC. |
| `backend/config_views.py` | **created** | `_SettingsView` base class + 5 grouped-view subclasses (`GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings`). Pure declarations + delegating accessors. |
| `backend/config_settings.py` | **created** | `Settings` Pydantic model: 170+ field declarations, `model_config`, 8 instance methods (`get_database_url`, `get_prompt_template`, `get_target_patterns`, `get_source_patterns`, `get_target_lang_tags`, `get_source_lang_tags`, `get_translation_config_hash`, `get_safe_config`), 5 grouped-view properties. |
| `backend/config_singleton.py` | **created** | `get_settings()`, `reload_settings(overrides)`, `_settings` module-global cache, `_settings_lock`. |
| `backend/tests/test_config_refactor_safety.py` | **created** | Characterization tests added in Task 1 — pin behaviour that existing test files don't yet cover (Settings class import, instance methods, singleton/reload). |

---

## Task 1: Add characterization tests for the parts of `config.py` not yet pinned

Existing tests (`test_config.py`, `test_config_split.py`, `test_settings_views.py`) already cover the views, the existing re-exports, and most basic flat-attribute access. The gaps are: (a) importing `Settings` itself by class name from `config`, (b) the 8 instance methods on `Settings`, (c) the singleton+reload behaviour. We pin those before moving any code.

**Files:**
- Create: `backend/tests/test_config_refactor_safety.py`

- [ ] **Step 1: Write the characterization test file**

```python
# backend/tests/test_config_refactor_safety.py
"""Characterization tests for backend/config.py refactor (B1).

These tests pin behaviour of the parts of config.py NOT yet covered by
test_config.py / test_config_split.py / test_settings_views.py.

After every extraction step in plan 2026-04-18-b1-config-py-split.md
this file MUST keep passing without modification.
"""

import pytest


def test_settings_class_importable_from_config():
    """Settings (the class) must be importable from `config`."""
    from config import Settings

    assert Settings is not None
    # Sanity: it is the Pydantic model, not a re-export of something else.
    assert hasattr(Settings, "model_config")
    assert hasattr(Settings, "model_dump")


def test_settings_instantiable_without_env():
    """Default-constructed Settings produces sensible values."""
    from config import Settings

    s = Settings()
    assert s.port == 5765
    assert s.target_language == "de"
    assert s.source_language == "en"


def test_get_database_url_sqlite_default():
    from config import Settings

    s = Settings(database_url="", db_path="/tmp/x.db")
    assert s.get_database_url() == "sqlite:////tmp/x.db"


def test_get_database_url_explicit_takes_precedence():
    from config import Settings

    s = Settings(database_url="postgresql://u:p@h/db", db_path="/tmp/x.db")
    assert s.get_database_url() == "postgresql://u:p@h/db"


def test_get_target_patterns_returns_dotted_extensions():
    from config import Settings

    s = Settings(target_language="de")
    patterns = s.get_target_patterns(fmt="ass")
    # Must include at least the iso 639-1 form
    assert ".de.ass" in patterns
    # And start with a dot
    assert all(p.startswith(".") for p in patterns)


def test_get_source_patterns_uses_source_language():
    from config import Settings

    s = Settings(source_language="en")
    patterns = s.get_source_patterns(fmt="srt")
    assert ".en.srt" in patterns


def test_get_target_lang_tags_returns_set_of_strings():
    from config import Settings

    s = Settings(target_language="de")
    tags = s.get_target_lang_tags()
    assert isinstance(tags, set)
    assert "de" in tags


def test_get_source_lang_tags_returns_set_of_strings():
    from config import Settings

    s = Settings(source_language="en")
    tags = s.get_source_lang_tags()
    assert isinstance(tags, set)
    assert "en" in tags


def test_get_translation_config_hash_is_12_chars_hex():
    from config import Settings

    s = Settings()
    h = s.get_translation_config_hash()
    assert isinstance(h, str)
    assert len(h) == 12
    int(h, 16)  # raises if not hex


def test_get_translation_config_hash_changes_with_model():
    from config import Settings

    s1 = Settings(ollama_model="qwen2.5:14b-instruct")
    s2 = Settings(ollama_model="llama3:8b")
    assert s1.get_translation_config_hash() != s2.get_translation_config_hash()


def test_get_translation_config_hash_non_ollama_ignores_model():
    from config import Settings

    s1 = Settings(ollama_model="model-a")
    s2 = Settings(ollama_model="model-b")
    # For non-ollama backend the model field is irrelevant.
    assert s1.get_translation_config_hash("deepl") == s2.get_translation_config_hash("deepl")


def test_get_safe_config_masks_api_keys():
    from config import Settings

    s = Settings(opensubtitles_api_key="SECRET123", subdl_api_key="OTHER456")
    safe = s.get_safe_config()
    assert safe["opensubtitles_api_key"] == "***configured***"
    assert safe["subdl_api_key"] == "***configured***"


def test_get_safe_config_passes_through_non_sensitive():
    from config import Settings

    s = Settings(port=5765, target_language="de")
    safe = s.get_safe_config()
    assert safe["port"] == 5765
    assert safe["target_language"] == "de"


def test_get_safe_config_masks_passwords():
    from config import Settings

    s = Settings(addic7ed_password="hunter2")
    safe = s.get_safe_config()
    assert safe["addic7ed_password"] == "***configured***"


def test_get_safe_config_masks_database_url_when_set():
    from config import Settings

    s = Settings(database_url="postgresql://user:pw@host/db")
    safe = s.get_safe_config()
    assert safe["database_url"] == "***configured***"


def test_get_safe_config_empty_credentials_stay_empty_string():
    from config import Settings

    s = Settings(opensubtitles_api_key="")
    safe = s.get_safe_config()
    assert safe["opensubtitles_api_key"] == ""


def test_get_safe_config_masks_subkeys_in_arr_instances_json():
    import json as _json

    from config import Settings

    payload = _json.dumps([{"name": "Main", "url": "http://s/", "api_key": "ABC"}])
    s = Settings(sonarr_instances_json=payload)
    safe = s.get_safe_config()
    parsed = _json.loads(safe["sonarr_instances_json"])
    assert parsed[0]["api_key"] == "***configured***"
    assert parsed[0]["name"] == "Main"  # non-credential subkey untouched


def test_get_settings_returns_singleton():
    from config import get_settings

    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_reload_settings_replaces_singleton():
    from config import get_settings, reload_settings

    s1 = get_settings()
    s2 = reload_settings()
    # The singleton now points at the reloaded instance.
    assert get_settings() is s2
    # reload_settings() always constructs a fresh Settings(); not the prior cache.
    assert s2 is not s1


def test_reload_settings_applies_overrides_with_type_coercion():
    from config import reload_settings

    s = reload_settings(overrides={"port": "9999", "wanted_anime_only": "false"})
    assert s.port == 9999  # str → int
    assert s.wanted_anime_only is False  # str → bool


def test_reload_settings_ignores_unknown_keys():
    from config import reload_settings

    s = reload_settings(overrides={"there_is_no_such_field_xyz": "1"})
    assert not hasattr(s, "there_is_no_such_field_xyz")


def test_reload_settings_skips_invalid_values():
    from config import reload_settings

    # "abc" cannot be parsed into the int field `port` — must be silently skipped
    # so the rest of the settings still load.
    s = reload_settings(overrides={"port": "abc"})
    assert s.port == 5765  # default preserved


def test_grouped_view_classes_importable_from_config():
    """Already covered by test_settings_views.py but pinned here too for safety."""
    from config import (
        GeneralSettings,
        MediaServerSettings,
        ProviderSettings,
        ScanningSettings,
        TranslationSettings,
    )

    for cls in (
        GeneralSettings,
        TranslationSettings,
        ProviderSettings,
        MediaServerSettings,
        ScanningSettings,
    ):
        assert cls is not None
        assert hasattr(cls, "_fields")
        assert isinstance(cls._fields, frozenset)
        assert len(cls._fields) > 0


@pytest.fixture(autouse=True)
def _reset_singleton_after_test():
    """Make sure singleton state from this file does not leak into other tests."""
    yield
    # Force a clean reload so subsequent test files see a fresh Settings()
    from config import reload_settings

    reload_settings()
```

- [ ] **Step 2: Run the new test file in isolation, expect all tests to PASS on the unmodified codebase**

Run: `cd backend && python -m pytest tests/test_config_refactor_safety.py -v`
Expected: every test PASS. If any test fails on the unmodified codebase, the test is wrong (assumes behaviour the code does not have) — fix the test, do not change `config.py`.

- [ ] **Step 3: Run the entire test suite to confirm the new file does not break neighbours**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: same pass count as before plus the new tests' contribution. Zero new failures.

- [ ] **Step 4: Run ruff on the new test file**

Run: `cd backend && ruff check tests/test_config_refactor_safety.py && ruff format --check tests/test_config_refactor_safety.py`
Expected: no findings.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_config_refactor_safety.py
git commit -m "test(config): characterization tests pinning Settings class, methods, singleton (B1 prep)"
```

---

## Task 2: Extract `_SettingsView` and the 5 grouped-view subclasses to `config_views.py`

The view family (lines 554–769 of the current `config.py`, ~215 LOC) is pure declarative code — a base class plus five subclasses that each declare a `_fields` frozenset and inherit identical delegation logic. They have no other dependencies inside `config.py`. The `Settings` class only references them by name from the property accessors (`@property def general(self) -> "GeneralSettings"` etc.) — already a string forward-reference.

**Files:**
- Create: `backend/config_views.py`
- Modify: `backend/config.py:554-769` (delete the moved classes) and `backend/config.py:830-846` (add `from config_views import ...`)

- [ ] **Step 1: Create `backend/config_views.py` with the moved classes**

Move verbatim (no behaviour change). The TYPE_CHECKING guard avoids a circular import once `Settings` lives in `config_settings.py`.

```python
# backend/config_views.py
"""Read-only grouped views into the Settings model.

Each view exposes a curated subset of Settings fields by name. Attribute
access is delegated to the underlying Settings instance for fields listed
in the subclass's _fields frozenset; everything else raises AttributeError.

Importing rule: this module MUST NOT import from `config_settings` at
module level (would cause a circular import). The `Settings` parameter
of `_SettingsView.__init__` is duck-typed; type-checking only sees it
through TYPE_CHECKING.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config_settings import Settings


class _SettingsView:
    """Base for read-only Settings group views.

    Delegates attribute access to the parent Settings instance for fields
    declared in the subclass ``_fields`` tuple. Raises ``AttributeError``
    for any field not in ``_fields``.
    """

    _fields: frozenset[str] = frozenset()

    def __init__(self, settings: "Settings") -> None:
        object.__setattr__(self, "_s", settings)

    def __setattr__(self, name: str, value) -> None:
        raise AttributeError(f"{type(self).__name__!r} is read-only")

    def __getattr__(self, name: str):
        if name in self._fields:
            return getattr(self._s, name)
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")


class GeneralSettings(_SettingsView):
    """Infrastructure: port, logging, paths, DB, Redis, plugins, backup."""

    _fields = frozenset(
        (
            "port",
            "api_key",
            "log_level",
            "log_file",
            "log_format",
            "media_path",
            "db_path",
            "cors_origins",
            "database_url",
            "db_pool_size",
            "db_pool_max_overflow",
            "db_pool_recycle",
            "redis_url",
            "redis_cache_enabled",
            "redis_queue_enabled",
            "plugins_dir",
            "plugin_hot_reload",
            "backup_dir",
            "backup_retention_daily",
            "backup_retention_weekly",
            "backup_retention_monthly",
        )
    )


class TranslationSettings(_SettingsView):
    """LLM, translation languages, prompt template, glossary."""

    _fields = frozenset(
        (
            "source_language",
            "target_language",
            "source_language_name",
            "target_language_name",
            "prompt_template",
            "ollama_url",
            "ollama_model",
            "batch_size",
            "request_timeout",
            "temperature",
            "max_retries",
            "backoff_base",
            "translation_max_workers",
            "glossary_enabled",
            "glossary_max_terms",
        )
    )


class ProviderSettings(_SettingsView):
    """Provider credentials, rate limiting, circuit breaker, reranking."""

    _fields = frozenset(
        (
            "provider_priorities",
            "providers_enabled",
            "providers_hidden",
            "provider_search_timeout",
            "provider_cache_ttl_minutes",
            "provider_auto_prioritize",
            "provider_rate_limit_enabled",
            "dedup_on_download",
            "provider_dynamic_timeout_enabled",
            "provider_dynamic_timeout_min_samples",
            "provider_dynamic_timeout_multiplier",
            "provider_dynamic_timeout_buffer_secs",
            "provider_dynamic_timeout_min_secs",
            "provider_dynamic_timeout_max_secs",
            "provider_reranking_enabled",
            "provider_reranking_min_downloads",
            "provider_reranking_max_modifier",
            "circuit_breaker_failure_threshold",
            "circuit_breaker_cooldown_seconds",
            "provider_auto_disable_cooldown_minutes",
            "provider_rate_limit_throttle_minutes",
            "addic7ed_username",
            "addic7ed_password",
            "turkcealtyazi_username",
            "turkcealtyazi_password",
            "opensubtitles_api_key",
            "opensubtitles_username",
            "opensubtitles_password",
            "jimaku_api_key",
            "subdl_api_key",
            "github_token",
            "anti_captcha_provider",
            "anti_captcha_api_key",
            "release_group_prefer",
            "release_group_exclude",
            "release_group_prefer_bonus",
        )
    )


class MediaServerSettings(_SettingsView):
    """Sonarr, Radarr, Jellyfin/Plex/Kodi, path mapping, ffmpeg, metadata."""

    _fields = frozenset(
        (
            "sonarr_url",
            "sonarr_api_key",
            "sonarr_instances_json",
            "radarr_url",
            "radarr_api_key",
            "radarr_instances_json",
            "jellyfin_url",
            "jellyfin_api_key",
            "media_servers_json",
            "path_mapping",
            "streaming_enabled",
            "ffmpeg_timeout",
            "scan_metadata_engine",
            "scan_metadata_max_workers",
        )
    )


class ScanningSettings(_SettingsView):
    """Wanted system, upgrade, HI, webhooks, automation, standalone, AniDB, notifications."""

    _fields = frozenset(
        (
            "wanted_scan_interval_hours",
            "wanted_anime_only",
            "wanted_anime_movies_only",
            "wanted_scan_on_startup",
            "wanted_auto_extract",
            "wanted_auto_translate",
            "wanted_max_search_attempts",
            "use_embedded_subs",
            "scan_yield_ms",
            "wanted_search_interval_hours",
            "wanted_search_on_startup",
            "wanted_search_max_items_per_run",
            "wanted_search_order",
            "provider_budget_enabled",
            "provider_budget_stretch_mode",
            "scheduler_profile",
            "setup_wizard_completed",
            "wanted_adaptive_backoff_enabled",
            "wanted_backoff_base_hours",
            "wanted_backoff_cap_hours",
            "wanted_skip_srt_on_no_ass",
            "upgrade_enabled",
            "upgrade_min_score_delta",
            "upgrade_window_days",
            "upgrade_prefer_ass",
            "upgrade_scan_interval_hours",
            "hi_removal_enabled",
            "hi_preference",
            "forced_preference",
            "credit_threshold_sec",
            "op_window_sec",
            "webhook_delay_minutes",
            "webhook_auto_scan",
            "webhook_auto_search",
            "webhook_auto_translate",
            "jellyfin_play_translate_enabled",
            "auto_sync_after_download",
            "auto_sync_engine",
            "auto_nfo_export",
            "standalone_enabled",
            "standalone_scan_interval_hours",
            "standalone_debounce_seconds",
            "standalone_skip_extras",
            "tmdb_api_key",
            "tvdb_api_key",
            "tvdb_pin",
            "metadata_cache_ttl_days",
            "auto_cleanup_after_extract",
            "auto_cleanup_keep_languages",
            "auto_cleanup_keep_formats",
            "subtitle_trash_retention_days",
            "anidb_enabled",
            "anidb_cache_ttl_days",
            "anidb_custom_field_name",
            "anidb_fallback_to_mapping",
            "notification_urls_json",
            "notify_on_download",
            "notify_on_upgrade",
            "notify_on_batch_complete",
            "notify_on_error",
            "notify_manual_actions",
            "remux_trash_dir",
            "remux_backup_retention_days",
            "remux_use_reflink",
            "remux_arr_pause_enabled",
        )
    )


__all__ = [
    "_SettingsView",
    "GeneralSettings",
    "TranslationSettings",
    "ProviderSettings",
    "MediaServerSettings",
    "ScanningSettings",
]
```

- [ ] **Step 2: Remove the moved class definitions from `config.py` and add a re-export**

Edit `backend/config.py`:

1. Delete lines 554–769 inclusive (the entire block: `class _SettingsView:` through the end of `class ScanningSettings`).
2. Insert this import block immediately after the existing `Settings` class definition (right before the existing `# Singleton settings instance` comment, around what is now line ~553):

```python
# View classes — re-exported via this module for backwards compatibility.
from config_views import (  # noqa: E402, F401
    _SettingsView,
    GeneralSettings,
    TranslationSettings,
    ProviderSettings,
    MediaServerSettings,
    ScanningSettings,
)
```

The `noqa: E402` is because the import follows other code in the module; `F401` because the names appear unused at the module level (they ARE used, just from the property accessors via string forward references).

- [ ] **Step 3: Run the safety net + view-specific tests**

Run: `cd backend && python -m pytest tests/test_config_refactor_safety.py tests/test_settings_views.py tests/test_config.py tests/test_config_split.py -v`
Expected: all tests pass. If `test_settings_views.py` fails on a delegation test, the issue is most likely a stale import in `config.py` — re-check that the `from config_views import …` block is in place AND that the old class definitions are fully removed (no leftover stub).

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: same pass count as before Task 2 (no regressions, no new tests added in this task).

- [ ] **Step 5: Run ruff over the whole backend (per CLAUDE.md: never just changed files)**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: no new findings beyond the 5 pre-existing violations documented in memory.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/config_views.py
git commit -m "refactor(config): extract _SettingsView family to config_views.py (B1 step 1/3)"
```

---

## Task 3: Extract `Settings` Pydantic class to `config_settings.py`

The `Settings` class (~390 LOC) holds field declarations + 8 instance methods + 5 grouped-view property accessors. It depends on:
- `pydantic_settings.BaseSettings` (external)
- `_get_language_tags` from `config_language_data` (already a separate module)
- `get_default_prompt_preset` from `db.translation` (lazy import inside method, unchanged)
- `hashlib` and `logging` (stdlib)
- The 5 view classes from `config_views` (extracted in Task 2)

Nothing inside `Settings` references `_settings`, `get_settings`, or `reload_settings`, so this extraction is independent of Task 4.

**Files:**
- Create: `backend/config_settings.py`
- Modify: `backend/config.py:14-552` (delete the moved class) and `backend/config.py` top (add `from config_settings import Settings`)

- [ ] **Step 1: Create `backend/config_settings.py` with the moved class**

Move the `Settings` class verbatim. Imports at the top of the new file include only what `Settings` needs.

```python
# backend/config_settings.py
"""Sublarr application settings — Pydantic model.

Holds the declarative field definitions, the 8 instance methods used by
the rest of the app, and the 5 grouped-view property accessors.

Importing rules:
- This module imports `config_views` for the property accessor return
  types — `config_views` does NOT import back (TYPE_CHECKING guard).
- Singleton management lives in `config_singleton.py`; this module does
  NOT cache instances.
"""

import hashlib
import logging

from pydantic_settings import BaseSettings

from config_language_data import _get_language_tags
from config_views import (
    GeneralSettings,
    MediaServerSettings,
    ProviderSettings,
    ScanningSettings,
    TranslationSettings,
)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Sublarr application settings.

    All fields can be overridden via SUBLARR_-prefixed env vars or a .env
    file. See backend/config.py for the public re-export surface.
    """

    # General
    port: int = 5765
    api_key: str = ""  # Empty = no auth required
    log_level: str = "INFO"
    log_file: str = (
        "log/sublarr.log"  # In-Repo default; Docker: set SUBLARR_LOG_FILE=/config/sublarr.log
    )
    media_path: str = "/media"
    db_path: str = "/config/sublarr.db"
    # Comma-separated allowed CORS/WebSocket origins (e.g. "https://app.example.com")
    # Defaults to localhost dev origins; set "*" only in fully trusted environments.
    cors_origins: str = "http://localhost:5173,http://localhost:5765"

    # === COPY ALL field declarations from current config.py lines 33–396 verbatim ===
    # === COPY model_config from current config.py lines 397–402 verbatim ===
    # === COPY all 8 methods from current config.py lines 404–524 verbatim ===
    # === COPY all 5 property accessors from current config.py lines 526–552 verbatim ===


__all__ = ["Settings"]
```

**IMPORTANT for the engineer executing the plan:** the `# === COPY … ===` comments above are placeholder reminders to the implementer — they MUST be replaced with the actual lines copied from the current `backend/config.py`. Open the current file at lines 33–552 and paste all of those lines into this file in place of the four placeholder comments. Do not paraphrase, do not "improve" the code, do not change formatting; the diff for Task 3 is a pure move.

After the copy, the bottom of the `Settings` class — specifically the property accessors — references the view classes by string forward-reference (`-> "GeneralSettings"`). Because the view classes are imported at the top of this new file, the forward references resolve naturally. No code change needed in those accessors.

- [ ] **Step 2: Remove `Settings` from `config.py` and add a re-export**

Edit `backend/config.py`:

1. Delete lines 7–12 (the `import hashlib`/`import logging`/`logger = ...`/`import threading` cluster that fed `Settings`) — but keep `import threading` if it is still needed for the singleton lock that lives in `config.py` until Task 4. So delete only `import hashlib`, `import logging`, and the `logger = logging.getLogger(__name__)` line. Keep `import threading`.
2. Delete the empty line + `from pydantic_settings import BaseSettings` (currently line 14).
3. Delete the entire `class Settings(BaseSettings):` block — currently lines 17–552 (everything up to and including the last property accessor `def scanning(self)`).
4. Insert at the position where `Settings` used to start:

```python
# Settings class — re-exported via this module for backwards compatibility.
from config_settings import Settings  # noqa: E402, F401
```

After this step, `config.py` should contain (in order): module docstring, `import threading`, the `from config_views import …` block from Task 2, the new `from config_settings import Settings` line, the unchanged singleton section (`_settings`, `_settings_lock`, `get_settings`, `reload_settings` — still inline, removed in Task 4), and the existing tail of `from config_instances import …`/`from config_language_data import …`/`from config_utils import map_path` re-exports.

The singleton functions (`get_settings`, `reload_settings`) still inside `config.py` reference `Settings` — that reference is now resolved by the re-export. No edits needed to those functions in this task.

- [ ] **Step 3: Run the safety net + Settings-related tests**

Run: `cd backend && python -m pytest tests/test_config_refactor_safety.py tests/test_settings_views.py tests/test_config.py tests/test_config_split.py -v`
Expected: all tests pass.

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: same pass count as before Task 3.

- [ ] **Step 5: Run ruff**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: no new findings.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/config_settings.py
git commit -m "refactor(config): extract Settings class to config_settings.py (B1 step 2/3)"
```

---

## Task 4: Extract singleton management (`get_settings`, `reload_settings`) to `config_singleton.py`

What remains inline in `config.py` after Task 3 is the singleton section: `_settings: Settings | None = None`, `_settings_lock = threading.Lock()`, `def get_settings()`, `def reload_settings(overrides=None)`. About 60 LOC. Moving this finishes the split.

**Files:**
- Create: `backend/config_singleton.py`
- Modify: `backend/config.py` (delete the singleton block, add re-export, drop `import threading`)

- [ ] **Step 1: Create `backend/config_singleton.py` with the moved code**

```python
# backend/config_singleton.py
"""Process-wide singleton accessor for Settings.

Other modules call `get_settings()` to retrieve the active Settings
instance and `reload_settings(overrides=...)` to swap it (e.g. after the
user saves config_entries via the UI).

Importing rule: this module imports `Settings` from `config_settings` at
top level — never the other way round.
"""

import threading

from config_settings import Settings

_settings: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    """Get or create the singleton Settings instance (thread-safe)."""
    global _settings
    if _settings is not None:
        return _settings
    with _settings_lock:
        if _settings is not None:
            return _settings
        _settings = Settings()
        return _settings


def reload_settings(overrides: dict | None = None) -> Settings:
    """Force reload settings from environment/file, with optional DB overrides.

    Args:
        overrides: Dict of key-value pairs (from DB config_entries) to apply
                   on top of the env/file settings.
    """
    global _settings
    base = Settings()
    new_settings = base

    if overrides:
        # Build update dict with correct types
        base_data = base.model_dump()
        update = {}
        for key, value in overrides.items():
            if key not in base_data:
                continue
            # Convert string values from DB to the correct field type
            expected_type = type(base_data[key])
            try:
                if expected_type is bool:
                    update[key] = (
                        value.lower() in ("true", "1", "yes")
                        if isinstance(value, str)
                        else bool(value)
                    )
                elif expected_type is int:
                    update[key] = int(value)
                elif expected_type is float:
                    update[key] = float(value)
                else:
                    update[key] = str(value).strip()
            except (ValueError, TypeError):
                continue  # Skip invalid values

        if update:
            new_settings = base.model_copy(update=update)

    with _settings_lock:
        _settings = new_settings

    return _settings


__all__ = ["get_settings", "reload_settings"]
```

Note: the `dict | None = None` parameter annotation replaces the original `dict = None`. The original was a latent bug (`dict` is not the same as `dict | None`); this is a strict-typing improvement that keeps the runtime behaviour identical (default `None` and an `if overrides:` guard).

- [ ] **Step 2: Remove the singleton block from `config.py`, drop the now-unused `import threading`, add a re-export**

Edit `backend/config.py`:

1. Delete the comment block + the four lines starting `_settings: Settings | None = None` through the end of the `reload_settings` function.
2. Delete `import threading` at the top — no longer needed in this file.
3. Insert at the position where the singleton block used to start:

```python
# Singleton accessors — re-exported via this module for backwards compatibility.
from config_singleton import get_settings, reload_settings  # noqa: E402, F401
```

Final state of `backend/config.py` should now be roughly:

```python
"""Centralized configuration using Pydantic Settings.

All settings can be overridden via environment variables with the SUBLARR_ prefix,
or via a .env file. Example: SUBLARR_PORT=8080
"""

# View classes — re-exported via this module for backwards compatibility.
from config_views import (  # noqa: E402, F401
    _SettingsView,
    GeneralSettings,
    TranslationSettings,
    ProviderSettings,
    MediaServerSettings,
    ScanningSettings,
)

# Settings class — re-exported via this module for backwards compatibility.
from config_settings import Settings  # noqa: E402, F401

# Singleton accessors — re-exported via this module for backwards compatibility.
from config_singleton import get_settings, reload_settings  # noqa: E402, F401

# ─── Re-exports for backwards compatibility ──────────────────────────────────
from config_instances import (  # noqa: E402, F401
    get_media_server_instances,
    get_radarr_instances,
    get_sonarr_instances,
    is_standalone_mode,
)
from config_language_data import (  # noqa: E402, F401
    _LANGUAGE_TAGS,
    SUPPORTED_LANGUAGES,
    _get_language_tags,
)
from config_utils import map_path  # noqa: E402, F401
```

Approximately 30 LOC including blank lines and comments — well below the 600 LOC target.

- [ ] **Step 3: Run the safety net + singleton-relevant tests**

Run: `cd backend && python -m pytest tests/test_config_refactor_safety.py tests/test_settings_views.py tests/test_config.py tests/test_config_split.py -v`
Expected: all tests pass — in particular `test_get_settings_returns_singleton`, `test_reload_settings_replaces_singleton`, `test_reload_settings_applies_overrides_with_type_coercion`.

- [ ] **Step 4: Run the full backend test suite**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: same pass count as before Task 4.

- [ ] **Step 5: Run ruff**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: no new findings.

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/config_singleton.py
git commit -m "refactor(config): extract get_settings/reload_settings to config_singleton.py (B1 step 3/3)"
```

---

## Task 5: Pin the achievement with a guard test, verify CLAUDE.md, and run frontend smoke

The cross-cutting framework requires an observability metric — for B1 the metric is `wc -l backend/config.py < 600`. We pin it with a unit test so a future change cannot regress the file silently.

**Files:**
- Modify: `backend/tests/test_config_refactor_safety.py` (add the LOC guard test)
- Verify (read-only): `D:\Sublarr_Projekt\Sublarr\CLAUDE.md`, `D:\Sublarr_Projekt\CLAUDE.md`

- [ ] **Step 1: Add the LOC-guard test to `test_config_refactor_safety.py`**

Append to the existing file `backend/tests/test_config_refactor_safety.py`:

```python
def test_config_py_under_600_loc():
    """Pin B1 achievement: config.py must stay below 600 LOC.

    If you are adding settings, put new fields in config_settings.py.
    If you are adding view classes, put them in config_views.py.
    config.py is intentionally a thin re-export façade.
    """
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "config.py"
    assert config_path.exists(), f"config.py not found at {config_path}"
    line_count = sum(1 for _ in config_path.open(encoding="utf-8"))
    assert line_count < 600, (
        f"backend/config.py is {line_count} LOC, must stay below 600. "
        "Move declarations into config_settings.py or config_views.py."
    )
```

- [ ] **Step 2: Run the guard test**

Run: `cd backend && python -m pytest tests/test_config_refactor_safety.py::test_config_py_under_600_loc -v`
Expected: PASS. If it FAILS with a line count above 600, Tasks 2/3/4 left orphan declarations behind — re-inspect `backend/config.py` and move any leftover code into the right sibling module.

- [ ] **Step 3: Read both `CLAUDE.md` files and check for stale references to internal `config.py` structure**

Read: `D:\Sublarr_Projekt\Sublarr\CLAUDE.md` and `D:\Sublarr_Projekt\CLAUDE.md`.

Look for: any text that names internal classes/functions of `config.py` in a way that implies they live in `config.py` (e.g. "edit `config.py` to add a Settings field"). The file ALREADY says "config.py # Pydantic settings (env vars with SUBLARR_ prefix)" which remains accurate — Pydantic settings are still importable from `config.py` (just re-exported). No change needed for that phrasing.

If you find a stale reference (a sentence that would mislead a reader after the split), edit the relevant `CLAUDE.md` file to say where the symbol now lives (`config_settings.py` for fields, `config_views.py` for groups, `config_singleton.py` for the accessors).

If both `CLAUDE.md` files are accurate as-is, leave them alone — do not invent gratuitous edits.

- [ ] **Step 4: Frontend regression smoke (config endpoints power the Settings UI)**

The Settings UI consumes `/api/v1/config` which reads via `Settings` and `get_safe_config`. Run the frontend test suite to verify the contract still holds end-to-end through the API serializer.

Run: `cd frontend && npm run test -- --run`
Expected: same pass count as before. If a frontend test that hits the config endpoint fails, the most likely cause is a missed re-export or an env-var coupling broken by the split — re-inspect `backend/config.py`.

- [ ] **Step 5: Final full backend test run + ruff**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance && ruff check . && ruff format --check .`
Expected: green.

- [ ] **Step 6: Commit (test guard + any CLAUDE.md edits)**

```bash
git add backend/tests/test_config_refactor_safety.py
# Conditionally include CLAUDE.md only if it was actually modified in step 3:
git add -u D:/Sublarr_Projekt/Sublarr/CLAUDE.md D:/Sublarr_Projekt/CLAUDE.md 2>/dev/null || true
git commit -m "test(config): pin config.py <600 LOC + verify docs (B1 complete)"
```

---

## Acceptance criteria

After all 5 tasks:

- `backend/config.py` is under 600 LOC (target: ~30, max: 600).
- `backend/config_views.py`, `backend/config_settings.py`, `backend/config_singleton.py` exist as new modules.
- Public import surface from `config.py` is unchanged: `Settings`, `get_settings`, `reload_settings`, `_SettingsView`, `GeneralSettings`, `TranslationSettings`, `ProviderSettings`, `MediaServerSettings`, `ScanningSettings`, `_get_language_tags`, `_LANGUAGE_TAGS`, `SUPPORTED_LANGUAGES`, `get_media_server_instances`, `get_radarr_instances`, `get_sonarr_instances`, `is_standalone_mode`, `map_path` — every one of these is still importable from `config`.
- `backend/tests/test_config_refactor_safety.py` exists with ≥ 23 tests, all passing.
- `cd backend && python -m pytest --tb=short -q --ignore=tests/performance` reports the same number of passed tests as on master before this plan, plus the new safety-net tests.
- `cd backend && ruff check . && ruff format --check .` reports no new findings.
- `cd frontend && npm run test -- --run` is green.

---

## Out of scope for this plan (handled in subsequent B1 sub-plans)

- The other 7 god-files (`backend/routes/cleanup.py`, `backend/providers/__init__.py`, `backend/providers/search_coordinator.py`, `backend/routes/wanted/extract.py`, `backend/routes/standalone.py`, `frontend/src/pages/SeriesDetail.tsx`, `frontend/src/hooks/useSystemApi.ts`) each get their own plan in subsequent `/deploy` cycles per spec §6.
- A generalized CI guard `tools/check_loc_limits.py` that fails on any backend file over 800 LOC. Adding it now would fail for the 7 files we have not split yet. Schedule for the final B1 sub-plan once all 8 files are below the cap.
- Bucket B Items B2 / B3 / B4 / B5 — separate plans.
