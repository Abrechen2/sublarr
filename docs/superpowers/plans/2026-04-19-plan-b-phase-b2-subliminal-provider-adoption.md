# Plan B / Phase B2 — Subliminal Provider Adoption

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B1 shipped as 0.64.0-beta — Subliminal vendor + adapter + `opensubtitles_subliminal` pilot.

**Goal:** Register Subliminal-flavor wrappers for the remaining 6 vendored Subliminal providers, bringing the registered provider count from 17 to 23.

**Scope correction vs. spec:** The spec estimated "~20 Subliminal providers" based on Bazarr's post-Subzero provider count. Vanilla Subliminal 2.2.0 actually vendors **7 providers total**: `addic7ed`, `gestdown`, `napiprojekt`, `opensubtitles` (pilot, already wrapped in B1), `opensubtitlescom`, `podnapisi`, `tvsubtitles`. This plan ships the 6 non-pilot providers. The spec's aggregate "≥35 providers after Plan B" target is not reachable from vanilla Subliminal alone — B3's Subzero selective merge must contribute more. Revised B2 outcome: 17 → 23 registered providers.

**Architecture:** Each Subliminal-flavor wrapper is a thin ~40-LOC module mirroring `backend/providers/subliminal_opensubtitles.py` from B1 — a subclass of `SubliminalProviderAdapter` that passes a specific Subliminal `Provider` class and declares the right `config_fields`/`languages`/`name`. Registry wiring adds one entry per module to `_BUILTIN_PROVIDERS`.

**Tech Stack:** Python 3.12, pytest, Subliminal 2.2.0 (vendored), the B1 `SubliminalProviderAdapter`.

**Baseline:** 0.64.0-beta → 0.65.0-beta (minor bump, B2).

---

## File Structure

### Create (wrapper modules — one per Subliminal provider)

- `backend/providers/subliminal_addic7ed.py` — wraps `subliminal.providers.addic7ed.Addic7edProvider`
- `backend/providers/subliminal_gestdown.py` — wraps `subliminal.providers.gestdown.GestdownProvider`
- `backend/providers/subliminal_napiprojekt.py` — wraps `subliminal.providers.napiprojekt.NapiProjektProvider`
- `backend/providers/subliminal_opensubtitlescom.py` — wraps `subliminal.providers.opensubtitlescom.OpenSubtitlesComProvider`
- `backend/providers/subliminal_podnapisi.py` — wraps `subliminal.providers.podnapisi.PodnapisiProvider`
- `backend/providers/subliminal_tvsubtitles.py` — wraps `subliminal.providers.tvsubtitles.TVsubtitlesProvider`

### Modify

- `backend/providers/registry.py` — add 6 entries at end of `_BUILTIN_PROVIDERS`

### Test

- `backend/tests/test_subliminal_provider_adoption.py` — parametrized registration + instantiation tests

---

## Task 1: Add 6 Subliminal-flavor wrapper modules

All 6 modules share the B1 pattern. They differ only in:
- Target Subliminal provider class import
- `name` attribute (kebab-case `<source>_subliminal`)
- `languages` set (per-provider language coverage)
- `config_fields` (auth requirements — varies)

**Files:** 6 create operations under `backend/providers/`.

- [ ] **Step 1: Create `backend/providers/subliminal_addic7ed.py`**

```python
"""Subliminal-flavor wrapper: Addic7ed.

Addic7ed is a scrape-based TV subtitle source requiring username+password.
Subliminal's implementation handles the HTML parsing + session auth.
Registered as 'addic7ed_subliminal' to coexist with Sublarr's native
'addic7ed' provider.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401 — side-effect import

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class Addic7edSubliminalProvider(SubliminalProviderAdapter):
    name = "addic7ed_subliminal"
    languages = {
        "en", "de", "es", "fr", "it", "pt", "ru", "pl", "cs", "da",
        "fi", "nl", "no", "sv", "tr", "zh", "ja", "ko", "ar", "he",
    }
    config_fields = [
        {"key": "username", "label": "Username", "type": "text", "required": True, "default": ""},
        {"key": "password", "label": "Password", "type": "password", "required": True, "default": ""},
    ]

    def __init__(self, **config):
        from subliminal.providers.addic7ed import Addic7edProvider

        super().__init__(
            subliminal_provider_cls=Addic7edProvider,
            provider_name="addic7ed_subliminal",
            **config,
        )
```

- [ ] **Step 2: Create `backend/providers/subliminal_gestdown.py`**

```python
"""Subliminal-flavor wrapper: Gestdown.

Gestdown is a free, unauthenticated TV subtitle API (successor to Addic7ed-API).
No config fields required.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class GestdownSubliminalProvider(SubliminalProviderAdapter):
    name = "gestdown_subliminal"
    languages = {
        "en", "de", "es", "fr", "it", "pt", "ru", "pl", "cs", "nl",
        "sv", "tr", "ja", "ko", "zh", "ar", "he",
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.gestdown import GestdownProvider

        super().__init__(
            subliminal_provider_cls=GestdownProvider,
            provider_name="gestdown_subliminal",
            **config,
        )
```

- [ ] **Step 3: Create `backend/providers/subliminal_napiprojekt.py`**

```python
"""Subliminal-flavor wrapper: NapiProjekt.

NapiProjekt is a free Polish-focused subtitle source. No auth.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class NapiProjektSubliminalProvider(SubliminalProviderAdapter):
    name = "napiprojekt_subliminal"
    languages = {"pl", "en"}
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.napiprojekt import NapiProjektProvider

        super().__init__(
            subliminal_provider_cls=NapiProjektProvider,
            provider_name="napiprojekt_subliminal",
            **config,
        )
```

- [ ] **Step 4: Create `backend/providers/subliminal_opensubtitlescom.py`**

```python
"""Subliminal-flavor wrapper: OpenSubtitles.com (REST API).

Distinct from:
- Sublarr's native `opensubtitles_fetch` (uses Sublarr's key-pool + budget manager)
- `opensubtitles_subliminal` (XML-RPC legacy, shipped in B1)

This flavor uses the official REST API via Subliminal's implementation.
Requires api_key, username, password.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class OpenSubtitlesComSubliminalProvider(SubliminalProviderAdapter):
    name = "opensubtitlescom_subliminal"
    languages = {
        "en", "de", "es", "fr", "it", "pt", "ru", "pl", "cs", "da",
        "fi", "nl", "no", "sv", "tr", "zh", "ja", "ko", "ar", "he",
        "el", "hu", "ro", "sk", "uk", "vi",
    }
    config_fields = [
        {"key": "apikey", "label": "API Key", "type": "password", "required": True, "default": ""},
        {"key": "username", "label": "Username", "type": "text", "required": True, "default": ""},
        {"key": "password", "label": "Password", "type": "password", "required": True, "default": ""},
    ]

    def __init__(self, **config):
        from subliminal.providers.opensubtitlescom import OpenSubtitlesComProvider

        super().__init__(
            subliminal_provider_cls=OpenSubtitlesComProvider,
            provider_name="opensubtitlescom_subliminal",
            **config,
        )
```

- [ ] **Step 5: Create `backend/providers/subliminal_podnapisi.py`**

```python
"""Subliminal-flavor wrapper: Podnapisi.

Free public subtitle source. No auth. Supports movies + TV.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class PodnapisiSubliminalProvider(SubliminalProviderAdapter):
    name = "podnapisi_subliminal"
    languages = {
        "en", "de", "es", "fr", "it", "pt", "ru", "pl", "cs", "da",
        "fi", "nl", "no", "sv", "tr", "zh", "ja", "ko", "ar", "he",
        "sl", "hr", "sr", "bg", "mk",
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.podnapisi import PodnapisiProvider

        super().__init__(
            subliminal_provider_cls=PodnapisiProvider,
            provider_name="podnapisi_subliminal",
            **config,
        )
```

- [ ] **Step 6: Create `backend/providers/subliminal_tvsubtitles.py`**

```python
"""Subliminal-flavor wrapper: TVsubtitles.

Scrape-based TV subtitle source. No auth.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class TVsubtitlesSubliminalProvider(SubliminalProviderAdapter):
    name = "tvsubtitles_subliminal"
    languages = {
        "en", "de", "es", "fr", "it", "pt", "ru", "pl", "cs", "nl",
        "sv", "tr", "ja", "ko", "zh", "ar", "he", "el", "hu", "ro",
    }
    config_fields = []

    def __init__(self, **config):
        from subliminal.providers.tvsubtitles import TVsubtitlesProvider

        super().__init__(
            subliminal_provider_cls=TVsubtitlesProvider,
            provider_name="tvsubtitles_subliminal",
            **config,
        )
```

- [ ] **Step 7: Run ruff format + check on the 6 new files**

Run:
```
cd backend && ruff format providers/subliminal_addic7ed.py providers/subliminal_gestdown.py providers/subliminal_napiprojekt.py providers/subliminal_opensubtitlescom.py providers/subliminal_podnapisi.py providers/subliminal_tvsubtitles.py
cd backend && ruff check providers/subliminal_addic7ed.py providers/subliminal_gestdown.py providers/subliminal_napiprojekt.py providers/subliminal_opensubtitlescom.py providers/subliminal_podnapisi.py providers/subliminal_tvsubtitles.py
```

Expected: both exit 0. If lint errors surface, fix them (e.g. unused import → remove).

- [ ] **Step 8: Commit**

```bash
git add backend/providers/subliminal_addic7ed.py backend/providers/subliminal_gestdown.py backend/providers/subliminal_napiprojekt.py backend/providers/subliminal_opensubtitlescom.py backend/providers/subliminal_podnapisi.py backend/providers/subliminal_tvsubtitles.py
git commit -m "feat(plan-b2): add 6 Subliminal-flavor provider wrappers"
```

---

## Task 2: Register the 6 providers in the builtin registry + add tests

**Files:**
- Modify: `backend/providers/registry.py`
- Create: `backend/tests/test_subliminal_provider_adoption.py`

- [ ] **Step 1: Write failing parametrized registration test**

```python
# backend/tests/test_subliminal_provider_adoption.py
"""Parametrized registration tests for Plan B2 Subliminal-flavor providers."""

import pytest

import providers._vendor  # noqa: F401 — trigger sys.path shim

from providers.subliminal_adapter import SubliminalProviderAdapter


B2_PROVIDER_MODULES = [
    "subliminal_addic7ed",
    "subliminal_gestdown",
    "subliminal_napiprojekt",
    "subliminal_opensubtitlescom",
    "subliminal_podnapisi",
    "subliminal_tvsubtitles",
]

B2_PROVIDER_NAMES = [
    "addic7ed_subliminal",
    "gestdown_subliminal",
    "napiprojekt_subliminal",
    "opensubtitlescom_subliminal",
    "podnapisi_subliminal",
    "tvsubtitles_subliminal",
]


@pytest.mark.parametrize("provider_name", B2_PROVIDER_NAMES)
def test_b2_provider_registered(provider_name):
    """Each B2 Subliminal-flavor provider must be registered after import_builtin_providers()."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert provider_name in _PROVIDER_CLASSES, (
        f"Expected '{provider_name}' in _PROVIDER_CLASSES, got: {sorted(_PROVIDER_CLASSES.keys())}"
    )


@pytest.mark.parametrize("provider_name", B2_PROVIDER_NAMES)
def test_b2_provider_instantiates_via_adapter(provider_name):
    """Each B2 provider must instantiate as a SubliminalProviderAdapter subclass."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    cls = _PROVIDER_CLASSES[provider_name]
    # Build kwargs that satisfy required config_fields
    kwargs = {f["key"]: "dummy" for f in cls.config_fields}
    instance = cls(**kwargs)
    assert isinstance(instance, SubliminalProviderAdapter)
    assert instance.name == provider_name


def test_b2_total_provider_count_meets_goal():
    """After B2 registration, the builtin registry holds ≥ 23 providers total."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert len(_PROVIDER_CLASSES) >= 23, (
        f"Expected ≥ 23 registered providers after B2, got {len(_PROVIDER_CLASSES)}: "
        f"{sorted(_PROVIDER_CLASSES.keys())}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_subliminal_provider_adoption.py -v`
Expected: all 13 tests FAIL with `KeyError` / `assertion error` — providers not yet in `_BUILTIN_PROVIDERS`.

- [ ] **Step 3: Register the 6 providers in `_BUILTIN_PROVIDERS`**

Edit `backend/providers/registry.py`. The current tuple ends with `"subliminal_opensubtitles"` (added in B1). Append the 6 new module names:

```python
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
    "subliminal_opensubtitles",
    # Plan B2 — Subliminal-flavor wrappers for the 6 non-pilot Subliminal providers
    "subliminal_addic7ed",
    "subliminal_gestdown",
    "subliminal_napiprojekt",
    "subliminal_opensubtitlescom",
    "subliminal_podnapisi",
    "subliminal_tvsubtitles",
)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_provider_adoption.py -v`
Expected: 13 tests PASS (6 registration + 6 instantiation + 1 aggregate count).

- [ ] **Step 5: Run the existing provider-related tests to verify no regression**

Run: `cd backend && python -m pytest tests/test_provider_registry.py tests/test_providers_init_refactor_safety.py tests/test_subliminal_opensubtitles_pilot.py -v --tb=short`
Expected: all PASS, no registrations broken.

- [ ] **Step 6: Ruff check**

Run: `cd backend && ruff check providers/registry.py tests/test_subliminal_provider_adoption.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/providers/registry.py backend/tests/test_subliminal_provider_adoption.py
git commit -m "feat(plan-b2): register 6 Subliminal-flavor providers + parametrized tests"
```

---

## Task 3: Pre-deploy verification + deploy

**Files:**
- Modify: `backend/VERSION` (in deploy step)
- Modify: `CHANGELOG.md` (in deploy step)

- [ ] **Step 1: Confirm pre-deploy checks green**

Run:

```bash
cd backend && ruff check .
cd backend && ruff format --check .
cd backend && python -m pytest tests/test_subliminal_provider_adoption.py tests/test_subliminal_opensubtitles_pilot.py tests/test_subliminal_adapter.py tests/test_subliminal_vendor.py tests/test_provider_registry.py tests/test_providers_init_refactor_safety.py -v --tb=short
```

All three must exit 0. The targeted test-subset (provider-related files) runs in under 30s and covers everything B2 touches — no need to wait for the 32-min full suite because B2 only adds wrapper modules and does not change the adapter or any non-provider code.

- [ ] **Step 2: Invoke the deploy skill**

Tell the orchestrator: **"Invoke the `deploy` skill."**

The skill:
1. Analyses commits since `0.64.0-beta` (the B1 ship — 2 feat: commits from B2)
2. Auto-bumps to `0.65.0-beta` (minor — B2 introduces new `feat:` commits)
3. Drafts a `CHANGELOG.md` entry `## [0.65.0-beta] - 2026-04-19`
4. Shows the version + changelog draft
5. Waits for confirmation
6. Writes `backend/VERSION` + `CHANGELOG.md`, commits, pushes
7. Builds multi-arch Docker, pushes to GHCR, deploys to Cardinal, health check + prune

Expected changelog prose (English):

```markdown
## [0.65.0-beta] - 2026-04-19

### Added
- **Plan B Phase 2 — Full Subliminal provider adoption** — Registered all 6
  remaining Subliminal providers via the B1 adapter: `addic7ed_subliminal`,
  `gestdown_subliminal`, `napiprojekt_subliminal`, `opensubtitlescom_subliminal`,
  `podnapisi_subliminal`, `tvsubtitles_subliminal`. Two are net-new to Sublarr
  (napiprojekt, opensubtitlescom), four are alternative flavors of existing
  native providers. Provider count: 17 → 23. Scope correction: vanilla
  Subliminal 2.2.0 ships 7 providers (not the ~20 originally estimated); the
  "≥ 35 providers after Plan B" goal depends on B3's Subzero selective merge.

### Plan B Progress
- Phase B2 — Full Subliminal provider adoption: **shipped**
```

- [ ] **Step 3: Verify provider count in prod**

After deploy, run:

```bash
curl -s -H "X-API-Key: $SUBLARR_API_KEY" http://192.168.178.36:5765/api/v1/providers/list \
  | python -c "import sys,json; d=json.load(sys.stdin); names=[p['name'] for p in d.get('providers', d)] if isinstance(d,(list,dict)) else []; print('count:', len(names)); [print(' -', n) for n in sorted(names) if 'subliminal' in n]"
```

Expected: `count: 23` (or more). At least 7 `*_subliminal` entries listed.

If `SUBLARR_API_KEY` is not set in the shell, pull it from the user's Sublarr Settings page and rerun.

- [ ] **Step 4: Tail prod logs for 60s**

```bash
ssh root@192.168.178.36 "docker logs sublarr --tail 200" | grep -iE "(error|traceback|exception)" | grep -v -E "(enzyme|has no X-Signature)" | head -20
```

Expected: no new B2-attributable errors. The known `enzyme` stevedore warning + the accepted F-05 `X-Signature` warning are pre-existing and filtered out.

---

## Phase B2 Acceptance Checklist

- [ ] 6 wrapper modules created under `backend/providers/subliminal_*.py`
- [ ] All 6 registered in `_BUILTIN_PROVIDERS`
- [ ] 13 parametrized tests pass (6 registration + 6 instantiation + 1 aggregate)
- [ ] No regression in existing provider-registry / init-refactor / B1 tests
- [ ] Ruff check + format clean
- [ ] 0.65.0-beta built + deployed to Cardinal
- [ ] `/api/v1/providers/list` shows ≥ 23 providers with ≥ 7 `*_subliminal` names

## Next Phase

**B3 — Subzero selective merge + granular blacklist.** Cherry-pick 3-5 providers/fixes from the Subzero fork that Subliminal 2.2 lacks, add file-hash dimension to the per-provider blacklist, push provider count toward ≥ 26.
