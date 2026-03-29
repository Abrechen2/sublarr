# Standalone Auto-Mode & Connection Settings Scan Button

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sublarr activates standalone mode automatically when no Sonarr/Radarr instances are configured, and exposes a manual "Scan Library" button in Connection Settings.

**Architecture:** A new backend helper `is_standalone_mode()` in `config.py` replaces all direct `standalone_enabled` checks with logic that also returns `True` when no arr instances exist. The status endpoint gains two new fields (`arr_configured`, `auto_activated`) that the frontend uses to render a contextual "Standalone" section in ConnectionsSettings — always visible, showing auto/manual state and a scan trigger.

**Tech Stack:** Python 3.12 (Flask), SQLAlchemy, pytest · React 19, TypeScript, React Query, Lucide icons, CSS variables

---

## File Map

| File | Change |
|------|--------|
| `backend/config.py` | Add `is_standalone_mode()` helper |
| `backend/standalone/__init__.py` | Replace `standalone_enabled` check with `is_standalone_mode()` |
| `backend/app.py` | Replace two `standalone_enabled` checks with `is_standalone_mode()` |
| `backend/routes/standalone.py` | Extend `get_status()` response with `arr_configured`, `auto_activated` |
| `backend/tests/test_standalone_auto_mode.py` | New test file |
| `frontend/src/lib/types.ts` | Extend `StandaloneStatus` with new fields |
| `frontend/src/pages/Settings/ConnectionsSettings.tsx` | Add `StandaloneSection` component |

---

## Task 1: Backend helper `is_standalone_mode()`

**Files:**
- Modify: `backend/config.py` (after `get_radarr_instances()`, ~line 1040)
- Create: `backend/tests/test_standalone_auto_mode.py`

### What the helper does

Returns `True` when standalone mode should be active:
- `standalone_enabled == True` (explicit opt-in), OR
- No Sonarr instances configured AND no Radarr instances configured (auto)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_standalone_auto_mode.py`:

```python
"""Tests for is_standalone_mode() auto-activation logic."""
from unittest.mock import patch, MagicMock


def _make_settings(standalone_enabled=False, sonarr_json="", radarr_json="",
                   sonarr_url="", sonarr_api_key="", radarr_url="", radarr_api_key=""):
    s = MagicMock()
    s.standalone_enabled = standalone_enabled
    s.sonarr_instances_json = sonarr_json
    s.radarr_instances_json = radarr_json
    s.sonarr_url = sonarr_url
    s.sonarr_api_key = sonarr_api_key
    s.radarr_url = radarr_url
    s.radarr_api_key = radarr_api_key
    s.path_mapping = ""
    return s


class TestIsStandaloneMode:
    def test_explicit_enabled_returns_true(self):
        from config import is_standalone_mode
        s = _make_settings(standalone_enabled=True)
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_no_arr_configured_auto_activates(self):
        from config import is_standalone_mode
        s = _make_settings()  # everything empty
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_sonarr_configured_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(
            sonarr_json='[{"id":"x","name":"S1","url":"http://host:8989","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_radarr_configured_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(
            radarr_json='[{"id":"x","name":"R1","url":"http://host:7878","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_legacy_sonarr_url_no_auto(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_url="http://host:8989", sonarr_api_key="key")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is False

    def test_explicit_enabled_overrides_arr_configured(self):
        """standalone_enabled=True activates even when arr IS configured."""
        from config import is_standalone_mode
        s = _make_settings(
            standalone_enabled=True,
            sonarr_json='[{"id":"x","name":"S1","url":"http://host:8989","api_key":"k"}]'
        )
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_empty_instances_json_array_no_arr(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_json="[]", radarr_json="[]")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True

    def test_invalid_json_treated_as_no_arr(self):
        from config import is_standalone_mode
        s = _make_settings(sonarr_json="not-valid-json")
        with patch("config.get_settings", return_value=s):
            assert is_standalone_mode() is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_standalone_auto_mode.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'is_standalone_mode' from 'config'`

- [ ] **Step 3: Implement `is_standalone_mode()` in `backend/config.py`**

Add after the `get_radarr_instances()` function (after line ~1040):

```python
def is_standalone_mode() -> bool:
    """Return True when standalone mode should be active.

    Standalone activates when:
    - ``standalone_enabled`` is explicitly True, OR
    - No Sonarr AND no Radarr instances are configured (auto-activation).
    """
    settings = get_settings()

    if getattr(settings, "standalone_enabled", False):
        return True

    # Auto-activate when no arr instances are configured
    return len(get_sonarr_instances()) == 0 and len(get_radarr_instances()) == 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_standalone_auto_mode.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_standalone_auto_mode.py
git commit -m "feat: add is_standalone_mode() helper — auto-activates when no arr configured"
```

---

## Task 2: Wire `is_standalone_mode()` into app startup

**Files:**
- Modify: `backend/app.py` (lines ~458, ~593)
- Modify: `backend/standalone/__init__.py` (line ~74)

- [ ] **Step 1: Replace check in `app.py` first block (~line 458)**

Change:
```python
if getattr(_get_standalone_settings(), "standalone_enabled", False):
```
To:
```python
from config import is_standalone_mode as _is_standalone_mode
if _is_standalone_mode():
```

Also remove the now-redundant `from config import get_settings as _get_standalone_settings` line if it is only used for this check.

- [ ] **Step 2: Replace check in `app.py` second block (~line 593)**

Change:
```python
if getattr(settings, "standalone_enabled", False):
```
To:
```python
from config import is_standalone_mode
if is_standalone_mode():
```

- [ ] **Step 3: Replace check in `standalone/__init__.py` `start()` method (~line 74)**

Change:
```python
if not getattr(settings, "standalone_enabled", False):
    logger.info("Standalone mode is disabled")
    return
```
To:
```python
from config import is_standalone_mode
if not is_standalone_mode():
    logger.info("Standalone mode is disabled (no arr configured and not explicitly enabled)")
    return
```

- [ ] **Step 4: Replace check in `standalone/__init__.py` `get_status()` method (~line 135)**

Change:
```python
enabled = getattr(get_settings(), "standalone_enabled", False)
```
To:
```python
from config import is_standalone_mode
enabled = is_standalone_mode()
```

- [ ] **Step 5: Run existing standalone tests to verify nothing broke**

```bash
cd backend && python -m pytest tests/ -k "standalone" --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py
```

Expected: all pass (or same failures as before this change)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/standalone/__init__.py
git commit -m "refactor: replace standalone_enabled checks with is_standalone_mode()"
```

---

## Task 3: Extend `/standalone/status` with `arr_configured` + `auto_activated`

**Files:**
- Modify: `backend/standalone/__init__.py` — `get_status()` method
- Modify: `backend/routes/standalone.py` — OpenAPI schema comment

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_standalone_auto_mode.py`:

```python
class TestStandaloneManagerStatus:
    def test_status_includes_arr_configured_and_auto_activated(self):
        """get_status() must return arr_configured and auto_activated fields."""
        from standalone import StandaloneManager
        mgr = StandaloneManager()

        sonarr_instances = [{"id": "x", "url": "http://host:8989", "api_key": "k"}]
        with (
            patch("config.get_settings", return_value=_make_settings(sonarr_json='[{"id":"x","url":"http://host:8989","api_key":"k"}]')),
            patch("config.is_standalone_mode", return_value=False),
            patch("db.standalone.get_watched_folders", return_value=[]),
        ):
            status = mgr.get_status()

        assert "arr_configured" in status
        assert "auto_activated" in status
        assert status["arr_configured"] is True
        assert status["auto_activated"] is False

    def test_status_auto_activated_when_no_arr(self):
        from standalone import StandaloneManager
        mgr = StandaloneManager()

        with (
            patch("config.get_settings", return_value=_make_settings()),
            patch("config.is_standalone_mode", return_value=True),
            patch("db.standalone.get_watched_folders", return_value=[]),
        ):
            status = mgr.get_status()

        assert status["arr_configured"] is False
        assert status["auto_activated"] is True
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && python -m pytest tests/test_standalone_auto_mode.py::TestStandaloneManagerStatus -v
```

Expected: FAIL — `arr_configured` key missing from status dict

- [ ] **Step 3: Extend `get_status()` in `backend/standalone/__init__.py`**

Replace the `return` statement at the end of `get_status()`:

```python
        try:
            from config import get_sonarr_instances, get_radarr_instances, is_standalone_mode
            arr_configured = (
                len(get_sonarr_instances()) > 0 or len(get_radarr_instances()) > 0
            )
            auto_activated = is_standalone_mode() and not getattr(
                get_settings(), "standalone_enabled", False
            )
        except Exception:
            arr_configured = False
            auto_activated = False

        return {
            "enabled": enabled,
            "watcher_running": self._watcher_running,
            "folders_count": folders_count,
            "scanner_scanning": self._scanner.is_scanning,
            "arr_configured": arr_configured,
            "auto_activated": auto_activated,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_standalone_auto_mode.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/standalone/__init__.py backend/tests/test_standalone_auto_mode.py
git commit -m "feat: extend standalone status with arr_configured and auto_activated fields"
```

---

## Task 4: Frontend — extend `StandaloneStatus` type

**Files:**
- Modify: `frontend/src/lib/types.ts` (after line ~543)

- [ ] **Step 1: Extend the interface**

In `frontend/src/lib/types.ts`, change:

```typescript
export interface StandaloneStatus {
  enabled: boolean
  watcher_running: boolean
  folders_count: number
  scanner_scanning: boolean
}
```

To:

```typescript
export interface StandaloneStatus {
  enabled: boolean
  watcher_running: boolean
  folders_count: number
  scanner_scanning: boolean
  arr_configured: boolean
  auto_activated: boolean
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -c "error" || echo "0 errors"
```

Expected: `0 errors`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat: extend StandaloneStatus type with arr_configured and auto_activated"
```

---

## Task 5: Frontend — `StandaloneSection` in ConnectionsSettings

**Files:**
- Modify: `frontend/src/pages/Settings/ConnectionsSettings.tsx`

### UI design

The section is always visible in Connections settings. It shows:

| State | Badge | Description |
|-------|-------|-------------|
| Auto-active (no arr) | green "Auto-aktiv" | "Kein Sonarr/Radarr konfiguriert — Standalone-Modus läuft automatisch." |
| Explicit enabled | green "Aktiv" | "Standalone-Modus ist manuell aktiviert." |
| Inactive (arr configured, not enabled) | gray "Inaktiv" | "Sonarr/Radarr konfiguriert. Standalone deaktiviert." |

Scan button:
- Label: "Bibliothek jetzt scannen"
- Icon: `ScanLine` (Lucide)
- Disabled + spinner when `scanner_scanning === true`
- Shows last result toast on success (series_found, movies_found, wanted_added)

Watched folders count shown as: `{folders_count} Ordner überwacht` (or "Keine Ordner konfiguriert" if 0).

- [ ] **Step 1: Add `ScanLine` to lucide import and `useStandaloneStatus` + `useTriggerStandaloneScan` hook imports**

In `ConnectionsSettings.tsx`, line ~20:

```typescript
import { Link, PlugZap, Server, Loader2, Plus, Pencil, TestTube, Trash2, Eye, EyeOff, Database, ScanLine } from 'lucide-react'
```

At the top of the file, add React Query hook imports (near existing hook imports, ~line 40):

```typescript
import { useStandaloneStatus, useTriggerStandaloneScan } from '@/hooks/useSystemApi'
```

- [ ] **Step 2: Write `StandaloneSection` component**

Add this component before the main `ConnectionsSettings` export function (around line ~510, after `MetadataApiKeysSection`):

```typescript
// ─── Standalone Section ───────────────────────────────────────────────────────

function StandaloneSection() {
  const { t } = useTranslation('settings')
  const { data: status } = useStandaloneStatus()
  const scan = useTriggerStandaloneScan()

  const isActive = status?.enabled ?? false
  const isAutoActivated = status?.auto_activated ?? false
  const isScanning = status?.scanner_scanning ?? false
  const foldersCount = status?.folders_count ?? 0

  function handleScan() {
    scan.mutate(undefined, {
      onSuccess: () => {
        toast.success('Scan gestartet')
      },
      onError: () => {
        toast.error('Scan konnte nicht gestartet werden')
      },
    })
  }

  return (
    <div className="space-y-4">
      {/* Status row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="text-sm font-medium px-2 py-0.5 rounded-full"
            style={{
              background: isActive
                ? 'color-mix(in srgb, var(--accent) 15%, transparent)'
                : 'color-mix(in srgb, var(--muted) 30%, transparent)',
              color: isActive ? 'var(--accent)' : 'var(--muted-foreground)',
            }}
          >
            {isAutoActivated
              ? 'Auto-aktiv'
              : isActive
              ? 'Aktiv'
              : 'Inaktiv'}
          </span>
          <span className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
            {foldersCount > 0
              ? `${foldersCount} Ordner überwacht`
              : 'Keine Ordner konfiguriert'}
          </span>
        </div>

        <button
          onClick={handleScan}
          disabled={isScanning || scan.isPending}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-sm font-medium transition-colors"
          style={{
            background: 'color-mix(in srgb, var(--accent) 12%, transparent)',
            color: 'var(--accent)',
            cursor: isScanning || scan.isPending ? 'not-allowed' : 'pointer',
            opacity: isScanning || scan.isPending ? 0.6 : 1,
          }}
        >
          {isScanning || scan.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ScanLine size={14} />
          )}
          {isScanning ? 'Scannt…' : 'Bibliothek jetzt scannen'}
        </button>
      </div>

      {/* Context description */}
      <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
        {isAutoActivated
          ? 'Kein Sonarr/Radarr konfiguriert — Standalone-Modus läuft automatisch. Watched Folders unter Einstellungen → Advanced → Library Sources konfigurieren.'
          : isActive
          ? 'Standalone-Modus ist manuell aktiviert.'
          : 'Sonarr/Radarr konfiguriert — Standalone-Modus ist inaktiv. Kann unter Advanced → Library Sources manuell aktiviert werden.'}
      </p>
    </div>
  )
}
```

- [ ] **Step 3: Add the `SettingsSection` block in the render**

In the `ConnectionsSettings` return JSX, add after the Media Servers section (before `{/* Metadata API Keys */}`):

```tsx
      {/* Standalone Mode */}
      <SettingsSection
        data-testid="standalone-section"
        title="Standalone-Modus"
        description="Bibliothek ohne Sonarr/Radarr verwalten"
        icon={<ScanLine size={16} style={{ color: 'var(--accent)' }} />}
      >
        <div className="py-3">
          <StandaloneSection />
        </div>
      </SettingsSection>
```

- [ ] **Step 4: Verify TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "ConnectionsSettings" | head -5
cd frontend && npm run lint 2>&1 | grep "ConnectionsSettings" | head -5
```

Expected: no errors

- [ ] **Step 5: Verify visually with dev server**

```bash
cd D:/Sublarr_Projekt/Sublarr && npm run dev
```

Open http://localhost:5173/settings/connections — confirm:
- "Standalone-Modus" section is visible
- Badge shows "Auto-aktiv" (since no arr configured locally, or check CT 101 after deploy)
- "Bibliothek jetzt scannen" button is clickable
- Clicking it triggers the scan (check network tab → `POST /api/v1/standalone/scan`)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Settings/ConnectionsSettings.tsx
git commit -m "feat: add StandaloneSection with scan button to Connection Settings"
```

---

## Task 6: Pre-PR checks + push

- [ ] **Step 1: Backend tests**

```bash
cd backend && python -m pytest --tb=short -q \
  --ignore=tests/performance \
  --ignore=tests/integration/test_provider_pipeline.py \
  --ignore=tests/test_video_sync.py \
  --ignore=tests/test_translation_backends.py \
  -k "not (test_sonarr_download_webhook or test_radarr_download_webhook or test_parse_llm_response_too_many_merge or test_record_backend_success)"
```

Expected: all pass

- [ ] **Step 2: Frontend checks**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

Expected: 0 errors

- [ ] **Step 3: Push**

```bash
git push origin master
```
