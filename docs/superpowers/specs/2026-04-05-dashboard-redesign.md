# Dashboard Redesign — Hybrid Activity-First × Mission Control

**Date:** 2026-04-05  
**Status:** Approved by user (visual mockup confirmed)

---

## Goal

Replace the current cluttered dashboard (AutomationBanner + HeroStats + NeedsAttentionCard + flexible widget grid) with a focused, fixed two-column layout that shows everything at once without scrolling and eliminates all duplicate information and known bugs.

---

## What Gets Removed

| Component | Reason |
|-----------|--------|
| `AutomationBanner` | Replaced by StatusStripe + "Run Now" in PageHeader |
| `HeroStats` | Replaced by MetricsRow |
| `NeedsAttentionCard` | Merged into ActivityFeed area as inline banner |
| `DashboardGrid` | Entire drag-and-drop widget grid removed |
| `WidgetSettingsModal` | No longer needed (no widget grid) |
| `WidgetWrapper` | No longer needed |
| `widgetRegistry.ts` | No longer needed |
| `dashboardStore.ts` | No longer needed (no layout persistence) |
| All 10 widget files in `widgets/` | Replaced by focused sidebar panels |

---

## New Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│  PageHeader: "Dashboard"              [▶ Jetzt starten] │  ← "Run Now" moves here
├─────────────────────────────────────────────────────────┤
│  ● AKTIV  Zuletzt: vor 4 Min  │ 3.412 │ 97% │ +14 │ 2  │  ← StatusStripe (1 line)
├─────────────────────────────────────────────────────────┤
│  3.412       │  2          │  87.4      │  5           │  ← MetricsRow (4 cells)
│  Untertitel  │  Fehlend    │  Ø Score   │  Low Score   │
├──────────────────────────────┬──────────────────────────┤
│  Aktivitäts-Feed             │  Provider-Status         │
│                              │  Service-Status          │
│  [⚠ Needs Attention — nur   │  Disk Space              │
│   wenn Items vorhanden]      │  Quick Actions           │
│                              │                          │
│  ● One Piece S01E04  91  2m  │                          │
│  ● Demon Slayer S03E01  8m   │                          │
│  ✗ AoT S02E01 — kein Match  │                          │
│  ...                         │                          │
│  ··· 40 weitere heute        │                          │
└──────────────────────────────┴──────────────────────────┘
│  Legende: ● Erfolg  ✗ Fehler  ◌ Läuft                        │
```

---

## New Components

### `StatusStripe`
- **File:** `frontend/src/components/dashboard/StatusStripe.tsx`
- **Data:** `useScannerStatus()`, `useStats()`, `useWantedSummary()`
- **Renders:** Pulsing green/gray dot + "AKTIV/PAUSIERT" + relative last-scan time + 4 inline stats (total subtitles, success rate, downloads today, missing count)
- **i18n:** All strings via `dashboard` namespace — no hardcoded English
- No "Pause" button (was no-op, removed entirely)

### `MetricsRow`
- **File:** `frontend/src/components/dashboard/MetricsRow.tsx`
- **Data:** `useStats()`, `useWantedSummary()`
- **Renders:** 4 borderless metric cells separated by vertical dividers
  - Untertitel gesamt (neutral color)
  - Fehlend / Stuck (warning color if > 0)
  - Ø Score (accent color)
  - Low Score Count (upgrade color if > 0)
- **Loading state:** Shows `—` placeholders while data loads (no false "0" flash)

### `ActivityFeed`
- **File:** `frontend/src/components/dashboard/ActivityFeed.tsx`
- **Data:** `useJobs(1, 20)` — refetches every 15s
- **Renders:**
  - Header: "Live Aktivitäts-Feed" + "Alle ansehen →" (links to `/activity`)
  - Inline `AttentionBanner` at top if `wantedSummary.total > 0`
  - List of job rows with color dot, truncated file path, status, relative time
  - Color coding: green = `completed`, red = `failed`, accent = `pending`/`running` (job data has no score field — orange/blue dots not feasible without backend changes)
  - "··· N weitere heute" footer if total > 20
  - Empty state: "Noch keine Aktivität heute"

### `AttentionBanner`
- **File:** `frontend/src/components/dashboard/AttentionBanner.tsx`
- **Data:** `useWantedItems(1, 5, undefined, undefined)` — fetches both `failed` AND `low_score` items (no status filter = all actionable)
- **Renders only when** `total > 0` — otherwise renders `null` (no empty card)
- Each row: series title + episode + reason + contextual action buttons
  - `failed` → "Suchen" (primary) + "Skip" (ghost)
  - `score < 50` → "Besser suchen" (primary) + "Annehmen" (ghost)
- "Alle ansehen →" links to `/wanted` (fix: was wrongly linking to `/activity`)
- **Bug fix:** Now fetches both failed AND low-score items (previously only `failed`)

### `DashboardSidebar`
- **File:** `frontend/src/components/dashboard/DashboardSidebar.tsx`
- Composed of 4 panels stacked vertically:

#### `ProviderHealthPanel`
- **Data:** `useProviders()` from `@/hooks/useApi` (same as existing `ProviderHealthWidget`)
- Status dot per enabled provider: green = healthy (success_rate ≥ 80%), red = unhealthy
- Compact dot + name + percentage list, max 5 providers

#### `ServiceStatusPanel`
- **Data:** Existing service status hook (from `ServiceStatusWidget`)
- Status dot per service: Sonarr, Radarr, Ollama
- Compact list

#### `DiskSpacePanel`
- **Data:** Existing disk space hook (from `DiskSpaceWidget`)
- Thin progress bar + "X GB / Y GB" label

#### `QuickActionsPanel`
- **Data:** `useRefreshWanted()`, `useStartWantedBatch()`, `useWantedBatchStatus()` (all from `@/hooks/useApi`)
- 2×2 grid of ghost buttons + 1 full-width primary CTA
- Actions: "Bibliothek scannen" (`useRefreshWanted`), "Batch-Suche starten" (`useStartWantedBatch`), "Wanted-Liste" (link to `/wanted`), "Logs" (link to `/activity`)
- Full-width: "▶ Automation jetzt ausführen" (same as "Bibliothek scannen", prominent CTA)

---

## Bugs Fixed

| Bug | Fix |
|-----|-----|
| Pause-Button war No-op | Button entfernt |
| "View All" → `/activity` statt `/wanted` | Link korrigiert zu `/wanted` |
| Low-Score Items nie angezeigt | `AttentionBanner` fetcht jetzt alle actionable Items |
| HeroStats zeigt "0" beim Laden | `MetricsRow` zeigt `—` Platzhalter |
| Hardcodierte englische Strings in AutomationBanner | Alle Strings i18n-iert |

---

## Data Sources (no new backend endpoints needed)

| Component | Hook | Endpoint |
|-----------|------|----------|
| StatusStripe | `useScannerStatus()`, `useStats()`, `useWantedSummary()` | Already exist |
| MetricsRow | `useStats()`, `useWantedSummary()` | Already exist |
| ActivityFeed | `useJobs(1, 20)` | Already exists |
| AttentionBanner | `useWantedItems(1, 5)` | Already exists |
| ProviderHealthPanel | Provider health hook | Already exists |
| ServiceStatusPanel | Service status hook | Already exists |
| DiskSpacePanel | Disk space hook | Already exists |
| QuickActionsPanel | `useRefreshWanted()` | Already exists |

No new backend endpoints required.

---

## Out of Scope

- The customizable widget grid is removed. If a future user requests per-user dashboard customization it would be a separate feature.
- No changes to any other pages (Library, Wanted, Activity, Settings, etc.)
- No changes to the backend.
- No new translations keys beyond what's needed for renamed/new strings.

---

## i18n Keys to Add

In `frontend/src/locales/de/dashboard.json` and `en/dashboard.json`:

```
dashboard.statusStripe.active
dashboard.statusStripe.paused
dashboard.statusStripe.lastScan
dashboard.statusStripe.neverScanned
dashboard.metrics.total
dashboard.metrics.missing
dashboard.metrics.avgScore
dashboard.metrics.lowScore
dashboard.feed.title
dashboard.feed.viewAll
dashboard.feed.empty
dashboard.feed.moreEvents
dashboard.attention.title
dashboard.attention.viewAll
dashboard.attention.search
dashboard.attention.skip
dashboard.attention.findBetter
dashboard.attention.accept
dashboard.sidebar.providers
dashboard.sidebar.services
dashboard.sidebar.disk
dashboard.sidebar.actions.scan
dashboard.sidebar.actions.upgrade
dashboard.sidebar.actions.wanted
dashboard.sidebar.actions.logs
dashboard.sidebar.actions.runNow
```

---

## File Changelist

**Delete:**
- `frontend/src/components/dashboard/AutomationBanner.tsx`
- `frontend/src/components/dashboard/HeroStats.tsx`
- `frontend/src/components/dashboard/NeedsAttentionCard.tsx`
- `frontend/src/components/dashboard/DashboardGrid.tsx`
- `frontend/src/components/dashboard/WidgetWrapper.tsx`
- `frontend/src/components/dashboard/WidgetSettingsModal.tsx`
- `frontend/src/components/dashboard/widgetRegistry.ts`
- `frontend/src/stores/dashboardStore.ts`
- `frontend/src/components/dashboard/widgets/` (entire directory)

**Create:**
- `frontend/src/components/dashboard/StatusStripe.tsx`
- `frontend/src/components/dashboard/MetricsRow.tsx`
- `frontend/src/components/dashboard/ActivityFeed.tsx`
- `frontend/src/components/dashboard/AttentionBanner.tsx`
- `frontend/src/components/dashboard/DashboardSidebar.tsx`

**Modify:**
- `frontend/src/pages/Dashboard.tsx` — rewired to new components
- `frontend/src/locales/de/dashboard.json` — new i18n keys
- `frontend/src/locales/en/dashboard.json` — new i18n keys
