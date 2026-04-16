# Phase 2 — User-Facing (wizard + dashboard + stretch mode) Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for execution. Tasks use checkbox (`- [ ]`) syntax.

**Spec:** `docs/superpowers/specs/2026-04-16-api-budget-scheduler-v1.md`

**Goal:** Make the V1 scheduler visible and configurable to users — first-run wizard, dashboard budget widget, hardware-profile presets, and stretch-mode smoothing.

**Architecture:** Extends Phase 1 without changing its contracts. New Flask routes for setup status + budget SocketIO emission. New React components for the wizard + widget. `scheduler_profile` setting maps to preset values of the Phase 1 config keys.

**Tech Stack:** Flask + SQLAlchemy + Flask-SocketIO, React + TypeScript + React Query + SocketIO-client.

---

## Task 1 — `scheduler_profile` config preset

**Files:**
- Modify: `backend/config.py` (new setting + preset application helper)
- Create: `backend/services/scheduler_profile.py` (profile → concrete setting values mapping)
- Create: `backend/tests/test_scheduler_profile.py`

**Presets:**
| Profile | `wanted_search_max_items_per_run` | `provider_budget_safety_margin_pct` | Target audience |
|---|---:|---:|---|
| `light` | 100 | 40 | Raspberry Pi, small NAS — minimal resource use |
| `balanced` (default) | 500 | 20 | Mid-range (N100, small ProxMox CT) |
| `aggressive` | 2000 | 10 | Unraid, multi-core server |
| `custom` | user-defined | user-defined | Power user overrides |

**Behaviour:** setting `scheduler_profile = "light"` applies the preset's values to the underlying keys. `custom` means "don't override" — other settings take precedence.

**Contract:** `apply_profile(profile: str) -> dict[str, Any]` returns the settings that would be applied (no side effect) so the UI can preview.

**Tests:** preset resolution for each profile; custom path returns empty; invalid profile raises `ValueError`.

---

## Task 2 — First-run wizard backend

**Files:**
- Create: `backend/routes/system/setup.py`
- Modify: `backend/routes/system/__init__.py` (register)
- Create: `backend/tests/test_routes_system_setup.py`

**Endpoints:**

### `GET /api/v1/system/setup/status`
```json
{
  "wizard_completed": false,
  "benchmark": {
    "cpu_count": 4,
    "ram_gb": 8,
    "os_test_ms": 350,
    "recommended_profile": "balanced"
  }
}
```
- `wizard_completed` persisted as config key `setup_wizard_completed: bool` (default `false`)
- `benchmark` computed on-the-fly: `os.cpu_count()` + `psutil.virtual_memory().total` + one OpenSubtitles ping timing (if configured; else skipped). Wrap the ping in try/except and default to 500ms on failure.
- `recommended_profile` rule: ≤2 cores or ≤2GB RAM → `light`; ≥8 cores and ≥8GB RAM → `aggressive`; else `balanced`.

### `POST /api/v1/system/setup/complete`
Body: `{"profile": "balanced" | "light" | "aggressive" | "custom"}`

- Applies the chosen profile (via the Task 1 helper) to settings
- Sets `setup_wizard_completed = true`
- Returns `{"ok": true, "applied": {...}}`

### `POST /api/v1/system/setup/reset` (dev/debug)
Resets `setup_wizard_completed = false`. Requires admin API key. Useful for QA.

---

## Task 3 — SocketIO `provider_budget_updated` event

**Files:**
- Modify: `backend/services/provider_budget.py` — emit after `consume()` / `refund()`
- Modify: `backend/extensions.py` (only if SocketIO needs exposure helper)
- Create: `backend/tests/test_provider_budget_socketio.py`

Emit a `provider_budget_updated` event with payload:
```json
{
  "provider": "opensubtitles",
  "usage": {"second": 0, "hour": 45, "day": 512},
  "limits": {"second": 5, "hour": 200, "day": 1000}
}
```

Emission is best-effort (fails silently if SocketIO is unavailable or not registered). Use the `emit_event()` helper from `events/__init__.py` if that pattern exists; otherwise directly via `socketio.emit`.

**Rate-limit the emission** — emit at most once per second per provider (use the per-second window as a natural cadence). The dashboard widget polls / subscribes at <=1Hz anyway.

---

## Task 4 — Stretch-mode pacing in budget manager

**Files:**
- Modify: `backend/services/provider_budget.py`
- Modify: `backend/tests/test_provider_budget.py`

**What stretch does:** spreads the daily budget evenly over 24 hours so the scheduler doesn't burn through OS-free's 1000 calls in the first 2 hours and then sit idle.

**Implementation:** a `stretch_allowed(provider, limits, now)` check that returns True only if current hour's consumption is below `limits["day"] / 24 × safety`. Called before the normal budget check — extra gate on top.

**Config:** `provider_budget_stretch_mode: str = "stretch"` values `stretch | burst | off`. Default `stretch`. `burst` disables the stretch gate. `off` disables the whole budget system (alias for `provider_budget_enabled=false` — keep both for clarity).

**Tests:** verify stretch allows spread usage and denies bursts.

---

## Task 5 — Frontend: Dashboard budget widget

**Files:**
- Create: `frontend/src/components/Dashboard/BudgetWidget.tsx`
- Create: `frontend/src/components/Dashboard/BudgetWidget.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx` (integrate widget)
- Modify: `frontend/src/i18n/locales/de/dashboard.json` + `en/dashboard.json` (new keys)

**Shape:**
```
┌─ API-Budget heute ─────────────────────┐
│ OpenSubtitles  ████████░░  820 / 1000  🟢 │
│ subdl          █████████▌   95 / 100   🟡 │
│ animetosho     ██░░░░░░░░  230 / 10000 🟢 │
│                                        │
│ ⏱ Reset in 4h 23min                    │
└────────────────────────────────────────┘
```

- One row per provider, sorted alphabetically
- Bar width = `usage.day / limits.day`
- Colour: green (<70%), yellow (70–90%), red (≥90%)
- Reset countdown = `reset_seconds.day` formatted as `Xh Ymin`
- Updates via polling every 5s (no SocketIO subscription yet — added in Task 3 via React Query `refetchInterval`)

**Data source:** `GET /api/v1/system/budget` (Phase 1 endpoint from commit `e25af01`).

**Test:** rendering with mocked data + 3 providers; bar widths; colour class on high-usage; empty-state when no providers.

---

## Task 6 — Frontend: First-run wizard modal

**Files:**
- Create: `frontend/src/components/Setup/FirstRunWizard.tsx`
- Create: `frontend/src/components/Setup/FirstRunWizard.test.tsx`
- Modify: `frontend/src/App.tsx` (mount the wizard at root, show conditionally)
- Modify: i18n files (new DE + EN strings for wizard)

**3 steps in modal:**
1. **Welcome** — intro text + "Deine Hardware wird geprüft" while backend benchmark loads
2. **Profile pick** — three buttons (Light / Balanced / Aggressive) with detected stats + recommendation highlighted; "Benutzerdefiniert" link opens advanced settings in a new tab
3. **Done** — confirmation with "Zum Dashboard" button

Backend calls: `GET /api/v1/system/setup/status` on mount, `POST .../complete` when user picks a profile.

Wizard is dismissable — but reappears on next session until user completes it OR explicitly clicks "Später". "Später" persists via `localStorage` (7 days) so it's per-browser, not persisted server-side (a returning user can still be nagged).

**Version-stamped showing for existing users:** the backend status endpoint returns `wizard_completed = false` by default. On v0.51 → V1 upgrade, the migration does NOT set it true. Existing users get the wizard at next login.

---

## Task 7 — Connect wizard trigger + SocketIO live updates

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx` — subscribe to `provider_budget_updated` via `useWebSocket` hook
- Modify: `frontend/src/App.tsx` — mount wizard gated on `/api/v1/system/setup/status.wizard_completed == false`
- Modify: `frontend/src/hooks/useWebSocket.ts` (if needed — add the new event name to the subscription list)

**SocketIO integration:**
- `useWebSocket('provider_budget_updated', payload => updateQueryCache(...))` in the dashboard widget component — patches the React Query cache so the bars update live.
- Poll remains as fallback (in case SocketIO drops).

**Test:** integration test that simulates a `provider_budget_updated` event and asserts the widget updates within 1s.

---

## Exit criteria for Phase 2

- [ ] 4 profiles selectable via first-run wizard
- [ ] Dashboard widget shows live per-provider bars
- [ ] `provider_budget_updated` events emitted on every consume/refund
- [ ] Stretch mode is default, testable toggle to burst
- [ ] Existing user on v0.51 → V1 upgrade sees the wizard on next session
- [ ] Full regression green (Phase 1 tests still pass)
