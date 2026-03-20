# Sublarr Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Sublarr frontend from 16 pages with 18 settings tabs into a streamlined 4-page layout (Dashboard, Library, Activity, Settings) with icon sidebar navigation, automation-first UX, and card-grid settings — while preserving every existing feature.

**Architecture:** Hybrid B+C design — Concept B's clean minimal layout with icon sidebar + Concept C's cinematic settings card-grid. Navigation reduced from 11 sidebar items to 3+1. Settings reorganized from 5 groups / 18 tabs into 8 category cards with drill-down detail pages. Activity consolidates 4 separate pages (Wanted, Queue, History, Blacklist) into one unified tabbed view. Translation is a togglable sub-feature inside General settings.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS v4, Lucide React icons, Inter font, React Query, Zustand, react-grid-layout, @tanstack/react-virtual, i18next (EN/DE), CodeMirror, Recharts

**Brand Guideline:** `docs/superpowers/brand-guideline.md`

**Approved Mockups:**
- `mockups/concept-final.html` — Dashboard, Library, Activity, Settings grid
- `mockups/concept-drilldown.html` — Settings detail (General) + Series detail

**Development Branch:** `feature/frontend-redesign` — all work happens on this branch. Old UI remains on `master` until redesign is fully verified and merged.

---

## Feature Migration Map

Every existing feature must survive the redesign. This table maps old location → new location.

| Old Page | Old Feature | New Location | Notes |
|----------|-------------|-------------|-------|
| Dashboard | Widget grid, stat cards, quick actions | Dashboard (redesigned) | New: automation banner, needs-attention card, hero stats |
| Dashboard | 10 widgets | Dashboard | Keep all, add automation widget prominence |
| Library | Grid/table view, search, filters | Library (enhanced) | Add score badges on posters, filter chips |
| Library | Bulk sync panel | Library | Keep, move to action bar |
| SeriesDetail | Episode list, actions, modals | Library → `/library/series/:id` | Add season summary bar, score per episode, color-coded rows |
| SeriesDetail | Subtitle editor, player, comparison | Library → Series detail (modals) | Keep all modals unchanged |
| SeriesDetail | Glossary, fansub prefs, audio tracks | Library → Series detail | Keep all inline features |
| SeriesDetail | Health check, OCR, sync | Library → Series detail (action menu) | Keep all |
| Wanted | Interactive search, batch ops | Activity → "Wanted" tab | Keep VirtualWantedTable |
| Queue | Job queue, progress bars | Activity → "In Progress" tab | Keep real-time updates |
| History | Download history, filters | Activity → "Completed" tab | Keep filter presets |
| Blacklist | Blacklist management | Activity → "Blacklist" tab | Keep pagination |
| Statistics | Charts, export, quality table | Dashboard widgets + Settings/System | Split: charts→dashboard, export→system |
| Tasks | Scheduler, run/cancel | Settings → Automation | Inline task cards |
| Logs | Virtual scroll, level filter | Settings → System | Inline log viewer |
| Plugins | Marketplace, install/uninstall | Settings → Providers | Merge with provider marketplace |
| Settings/General | Port, API key, log level, paths | Settings → General | Keep all fields |
| Settings/Sonarr,Radarr | Connection config | Settings → Connections | Connection cards |
| Settings/MediaServers | Jellyfin, Plex, Kodi | Settings → Connections | Connection cards |
| Settings/ApiKeys | API key management | Settings → Connections | Merge into connection cards |
| Settings/Languages | Source/target, HI prefs | Settings → General (interface section) | Move to General |
| Settings/Scoring | Weights, modifiers, presets | Settings → Subtitles | Keep all |
| Settings/SubtitleTools | Timing, fixes, preview | Settings → Subtitles | Keep all |
| Settings/Cleanup | Dedup, orphaned | Settings → Subtitles | Keep all |
| Settings/Providers | Provider list, priority, cache | Settings → Providers | Enhanced marketplace grid |
| Settings/Translation | Backends, prompts, glossary, memory | Settings → Translation | Conditionally visible |
| Settings/Whisper | STT config | Settings → Translation | Sub-section of translation |
| Settings/Automation | Re-ranking, upgrades, webhooks | Settings → Automation | Toggle cards |
| Settings/Wanted | Scan interval, anime filter | Settings → Automation | Merge into automation |
| Settings/Events | Hooks, webhooks | Settings → System | Keep CRUD interface |
| Settings/Backup | Full backup CRUD | Settings → System | Keep all |
| Settings/Integrations | External services | Settings → System | Keep all |
| Settings/Notifications | Templates, quiet hours | Settings → Notifications | Keep all |
| Settings/Security | Auth, CORS, rate limiting | Settings → System | Keep all |
| Settings/Protokoll | Request logging | Settings → System | Keep all |
| Settings/Migration | Import/export | Settings → System | Keep all |
| Settings/LanguageProfiles | Profile CRUD | Settings → Subtitles (advanced) | Keep all |

---

## File Structure (New & Modified)

### New Files to Create

```
frontend/src/
├── components/
│   ├── layout/
│   │   ├── IconSidebar.tsx           # New sidebar (replaces Sidebar.tsx)
│   │   ├── BottomNav.tsx             # Mobile bottom navigation
│   │   ├── PageHeader.tsx            # Reusable page header + breadcrumb
│   │   └── StatusBar.tsx             # Bottom status bar
│   ├── dashboard/
│   │   ├── AutomationBanner.tsx      # Automation status banner
│   │   ├── HeroStats.tsx             # 4 hero stat cards
│   │   └── NeedsAttentionCard.tsx    # Items needing manual intervention
│   ├── activity/
│   │   ├── ActivityTabs.tsx          # Pill tab switcher
│   │   ├── NeedsAttentionTab.tsx     # Attention items table
│   │   └── InProgressTab.tsx         # Active jobs with progress
NOTE: The existing `pages/Activity.tsx` (old jobs viewer) will be REPLACED
by the new `pages/ActivityPage.tsx`. Rename during Phase 4 to avoid conflicts.
│   ├── settings/
│   │   ├── SettingsGrid.tsx          # Card grid overview
│   │   ├── SettingsDetailLayout.tsx  # Breadcrumb + section layout
│   │   ├── SettingsSearch.tsx        # Global settings search
│   │   ├── FormGroup.tsx             # Label + control form row
│   │   ├── SettingsSection.tsx       # Section card with icon header
│   │   ├── ConnectionCard.tsx        # Service connection card
│   │   ├── FeatureAddon.tsx          # Feature toggle card (translation)
│   │   └── AutoSaveToast.tsx         # "Saved [Undo]" toast
│   ├── library/
│   │   ├── LibraryCard.tsx           # Grid card with score badge (replaces LibraryGridCard)
│   │   ├── SeasonSummaryBar.tsx      # Color-coded season progress
│   │   └── EpisodeRow.tsx            # Score-colored episode row
│   └── shared/
│       ├── FilterChips.tsx           # Horizontal scrollable chips
│       ├── PillTabs.tsx              # Segmented pill tabs
│       ├── Breadcrumb.tsx            # Navigation breadcrumb
│       └── ScoreBadge.tsx            # Color-coded score pill
├── pages/
│   ├── ActivityPage.tsx              # Unified activity (replaces 4 pages)
│   └── Settings/
│       ├── SettingsOverview.tsx       # Card grid (replaces index.tsx logic)
│       ├── GeneralSettings.tsx       # General detail page
│       ├── ConnectionsSettings.tsx   # Connections detail page
│       ├── SubtitlesSettings.tsx     # Subtitles detail page
│       ├── ProvidersSettings.tsx     # Providers detail page
│       ├── AutomationSettings.tsx    # Automation detail page
│       ├── TranslationSettings.tsx   # Translation detail page
│       ├── NotificationsSettings.tsx # Notifications detail page
│       └── SystemSettings.tsx        # System detail page
└── styles/
    └── (none — all in index.css + Tailwind)
```

### Files to Modify

```
frontend/src/index.css                 # Design tokens overhaul
frontend/src/App.tsx                   # Route restructuring
frontend/src/pages/Dashboard.tsx       # Add automation banner, hero stats, needs attention
frontend/src/pages/Library.tsx         # Filter chips, score badges, view improvements
frontend/src/pages/SeriesDetail.tsx    # Season summary, episode rows, breadcrumb
frontend/src/pages/Settings/index.tsx  # Router for settings sub-routes
frontend/src/components/layout/Sidebar.tsx  # Eventually replaced by IconSidebar
frontend/src/hooks/useApi.ts           # May need new hooks for automation status
frontend/src/i18n/locales/en/*.json    # New translation keys
frontend/src/i18n/locales/de/*.json    # New translation keys
```

### Files to Remove (After Migration Complete)

```
# Old standalone pages (replaced by Activity/Settings)
frontend/src/pages/Wanted.tsx          # → ActivityPage "Wanted" tab
frontend/src/pages/Queue.tsx           # → ActivityPage "In Progress" tab
frontend/src/pages/History.tsx         # → ActivityPage "Completed" tab
frontend/src/pages/Blacklist.tsx       # → ActivityPage "Blacklist" tab
frontend/src/pages/Activity.tsx        # → ActivityPage (new unified page replaces old jobs viewer)
frontend/src/pages/Statistics.tsx      # → Dashboard widgets + System settings
frontend/src/pages/Tasks.tsx           # → Automation settings
frontend/src/pages/Logs.tsx            # → System settings
frontend/src/pages/Plugins.tsx         # → Providers settings

# Old settings tab files (content extracted into new category pages)
# These are NOT removed until their content is fully migrated.
# Strategy: import and reuse existing tab internals where possible,
# then delete old shell files once new pages are verified.
frontend/src/pages/Settings/AdvancedTab.tsx         # → Split across Subtitles, Connections, System
frontend/src/pages/Settings/ApiKeysTab.tsx           # → Connections
frontend/src/pages/Settings/CleanupTab.tsx           # → Subtitles
frontend/src/pages/Settings/EventsTab.tsx            # → Subtitles (scoring) + System (hooks)
frontend/src/pages/Settings/IntegrationsTab.tsx      # → System
frontend/src/pages/Settings/MediaServersTab.tsx      # → Connections
frontend/src/pages/Settings/MigrationTab.tsx         # → System
frontend/src/pages/Settings/NotificationTemplatesTab.tsx  # → Notifications
frontend/src/pages/Settings/ProtokollTab.tsx         # → System
frontend/src/pages/Settings/ProvidersTab.tsx         # → Providers
frontend/src/pages/Settings/SecurityTab.tsx          # → System
frontend/src/pages/Settings/TranslationTab.tsx       # → Translation
frontend/src/pages/Settings/WhisperTab.tsx           # → Translation

# Old layout
frontend/src/components/layout/Sidebar.tsx           # → Replaced by IconSidebar
```

### Existing Components — Reuse vs. Replace

| Existing Component | Action | Notes |
|-------------------|--------|-------|
| `shared/SettingsCard.tsx` | **Keep** | Used as card container inside new settings pages |
| `shared/SettingRow.tsx` | **Replace** with `settings/FormGroup.tsx` | New layout (label-left, control-right) |
| `shared/SettingSection.tsx` | **Replace** with `settings/SettingsSection.tsx` | New design with icon header |
| `shared/ScoreBreakdown.tsx` | **Keep** | Detailed breakdown tooltip — coexists with new `ScoreBadge.tsx` (simple pill) |
| `shared/Toast.tsx` | **Keep** | `AutoSaveToast` is a specialized wrapper around existing Toast system |
| `library/LibraryGridCard.tsx` | **Replace** with `library/LibraryCard.tsx` | New design with score badge |

### Pre-Implementation Audit

Before starting Phase 2, audit existing hook return values against mockup data requirements:

| Mockup Data Point | Required Hook | Field to Check | If Missing |
|-------------------|---------------|---------------|------------|
| Automation success rate | `useStats()` | `success_rate` or compute from `completed/total` | Add backend endpoint |
| Today's download count | `useStats()` | `today_downloads` or filter by date | Compute client-side from history |
| Next scan timer | `useScannerStatus()` | `next_run` or `interval_remaining` | May need new field |
| Needs attention count | `useWantedSummary()` | Failed + low-score items | Compute client-side |
| Low score count | `useStats()` or `useQualityTrends()` | Items below threshold | Compute client-side |

---

## Phase 1: Foundation (Design Tokens + Layout Shell)

### Task 1.1: Update Design Tokens in index.css

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Add Inter font import**

Add at the top of `index.css`, after `@import "tailwindcss"`:

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
```

- [ ] **Step 2: Update CSS custom properties in `:root`**

Update the `:root` block with new tokens (keep existing color values, add new spacing/radius/animation tokens):

```css
:root {
  /* Backgrounds — Light */
  --bg-primary: #eff1f4;
  --bg-surface: #ffffff;
  --bg-surface-hover: #f5f7fa;
  --bg-elevated: #f9fafb;

  /* Borders — Light */
  --border: #dde0e8;
  --border-hover: #c6cad5;

  /* Text — Light */
  --text-primary: #18191f;
  --text-secondary: #525968;
  --text-muted: #8c95a6;

  /* Deep background (body-level, dark mode primarily) */
  --bg-deep: #eff1f4;   /* Light: same as bg-primary; Dark: overridden to #131519 */

  /* Brand — Sublarr Teal */
  --accent: #0f9bb5;
  --accent-hover: #0d8aa1;
  --accent-dim: #0a7089;
  --accent-subtle: rgba(15, 155, 181, 0.08);
  --accent-bg: rgba(15, 155, 181, 0.12);
  --accent-glow: rgba(15, 155, 181, 0.25);

  /* Status — Light */
  --success: #22a55b;
  --success-bg: rgba(34, 165, 91, 0.1);
  --error: #e5334b;
  --error-bg: rgba(229, 51, 75, 0.1);
  --warning: #d48a08;
  --warning-bg: rgba(212, 138, 8, 0.1);
  --upgrade: #7c3aed;
  --upgrade-bg: rgba(124, 58, 237, 0.10);

  /* Typography — NEW */
  --font-body: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;

  /* Radius — UPDATED (was 3-5px, now modern) */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;

  /* Spacing — NEW 8px grid */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  /* Shadows — NEW */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 2px 8px rgba(0,0,0,0.08);
  --shadow-lg: 0 4px 16px rgba(0,0,0,0.12);
  --shadow-glass: 0 4px 24px rgba(0,0,0,0.06);

  /* Animation — NEW */
  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 400ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

- [ ] **Step 3: Update `.dark` block with matching new tokens**

Add `--bg-deep`, `--accent-glow`, spacing, radius, shadow, animation tokens to `.dark`. Keep existing dark color values but add:

```css
.dark {
  /* ... existing dark colors stay ... */
  --bg-deep: #131519;  /* Deepest background for body */
  --accent-glow: rgba(29, 184, 212, 0.25);

  /* Same spacing/radius/shadow/animation tokens as :root */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.15);
  --shadow-md: 0 2px 8px rgba(0,0,0,0.25);
  --shadow-lg: 0 4px 16px rgba(0,0,0,0.35);
  --shadow-glass: 0 4px 24px rgba(0,0,0,0.2);
  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 400ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

- [ ] **Step 3b: Add @keyframes pulse animation for automation dot**

Add to `index.css` (may already exist — update if needed):

```css
@keyframes automationPulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px currentColor; }
  50% { opacity: 0.5; box-shadow: 0 0 8px currentColor, 0 0 12px currentColor; }
}
```

> **Note:** Brand guideline specifies `--radius-sm: 6px`. The mockup HTML files used `8px` but the guideline is the source of truth. Use `6px`.

- [ ] **Step 4: Verify existing components still render**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: No errors from token changes (custom properties are backward-compatible)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): update design tokens — Inter font, modern radii, spacing scale, shadows, animations"
```

---

### Task 1.2: Create Shared UI Primitives

**Files:**
- Create: `frontend/src/components/shared/Breadcrumb.tsx`
- Create: `frontend/src/components/shared/PillTabs.tsx`
- Create: `frontend/src/components/shared/FilterChips.tsx`
- Create: `frontend/src/components/shared/ScoreBadge.tsx`
- Test: `frontend/src/components/shared/__tests__/Breadcrumb.test.tsx`
- Test: `frontend/src/components/shared/__tests__/PillTabs.test.tsx`
- Test: `frontend/src/components/shared/__tests__/FilterChips.test.tsx`
- Test: `frontend/src/components/shared/__tests__/ScoreBadge.test.tsx`

- [ ] **Step 1: Write tests for Breadcrumb**

```tsx
// Breadcrumb.test.tsx
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Breadcrumb } from '../Breadcrumb';

describe('Breadcrumb', () => {
  it('renders segments with separator', () => {
    render(
      <BrowserRouter>
        <Breadcrumb items={[
          { label: 'Settings', href: '/settings' },
          { label: 'General' },
        ]} />
      </BrowserRouter>
    );
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('General')).toBeInTheDocument();
  });

  it('renders last item as non-link', () => {
    render(
      <BrowserRouter>
        <Breadcrumb items={[
          { label: 'Settings', href: '/settings' },
          { label: 'General' },
        ]} />
      </BrowserRouter>
    );
    const lastItem = screen.getByText('General');
    expect(lastItem.closest('a')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/components/shared/__tests__/Breadcrumb.test.tsx`
Expected: FAIL — module not found

- [ ] **Step 3: Implement Breadcrumb**

```tsx
// Breadcrumb.tsx
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs mb-4">
      {items.map((item, i) => (
        <span key={i} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={12} className="text-[var(--text-muted)]" />}
          {item.href ? (
            <Link to={item.href} className="text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors">
              {item.label}
            </Link>
          ) : (
            <span className="text-[var(--text-primary)] font-medium">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/components/shared/__tests__/Breadcrumb.test.tsx`
Expected: PASS

- [ ] **Step 5: Write tests for PillTabs, FilterChips, ScoreBadge**

Follow same TDD pattern: write test → verify fail → implement → verify pass. Each component:

**PillTabs:** Renders tabs, highlights active, calls onChange, shows badge count.
**FilterChips:** Renders chips, toggles active state, horizontal scroll container.
**ScoreBadge:** Renders score number, applies correct color class (high/medium/low/missing).

- [ ] **Step 6: Implement PillTabs**

```tsx
// PillTabs.tsx
interface PillTab {
  id: string;
  label: string;
  count?: number;
}

interface PillTabsProps {
  tabs: PillTab[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

export function PillTabs({ tabs, activeTab, onChange }: PillTabsProps) {
  return (
    <div className="flex gap-0.5 bg-[var(--bg-surface)] rounded-[var(--radius-md)] p-[3px] w-fit">
      {tabs.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-3.5 py-1.5 text-xs font-medium rounded-[7px] transition-all duration-150 ${
            activeTab === tab.id
              ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
        >
          {tab.label}
          {tab.count !== undefined && (
            <span className="ml-1 text-[10px] font-semibold text-[var(--accent)]">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 7: Implement FilterChips**

```tsx
// FilterChips.tsx
interface FilterChip {
  id: string;
  label: string;
}

interface FilterChipsProps {
  chips: FilterChip[];
  activeChip: string;
  onChange: (chipId: string) => void;
}

export function FilterChips({ chips, activeChip, onChange }: FilterChipsProps) {
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-none">
      {chips.map(chip => (
        <button
          key={chip.id}
          onClick={() => onChange(chip.id)}
          className={`px-3 py-1 rounded-full text-xs font-medium border whitespace-nowrap transition-all duration-150 ${
            activeChip === chip.id
              ? 'bg-[var(--accent-bg)] border-[var(--accent)] text-[var(--accent)]'
              : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]'
          }`}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 8: Implement ScoreBadge**

```tsx
// ScoreBadge.tsx
interface ScoreBadgeProps {
  score: number | null;
  className?: string;
}

export function ScoreBadge({ score, className = '' }: ScoreBadgeProps) {
  if (score === null) {
    return (
      <span className={`text-xs font-bold px-2.5 py-0.5 rounded-md bg-[var(--error-bg)] text-[var(--error)] ${className}`}>
        Missing
      </span>
    );
  }

  const variant = score >= 70
    ? 'bg-[var(--success-bg)] text-[var(--success)]'
    : score >= 50
      ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
      : 'bg-[var(--warning-bg)] text-[var(--warning)]';

  return (
    <span className={`text-xs font-bold px-2.5 py-0.5 rounded-md ${variant} ${className}`}>
      {score}
    </span>
  );
}
```

- [ ] **Step 9: Run all shared component tests**

Run: `cd frontend && npm run test -- --run src/components/shared/__tests__/`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/shared/Breadcrumb.tsx frontend/src/components/shared/PillTabs.tsx frontend/src/components/shared/FilterChips.tsx frontend/src/components/shared/ScoreBadge.tsx frontend/src/components/shared/__tests__/
git commit -m "feat(ui): add shared primitives — Breadcrumb, PillTabs, FilterChips, ScoreBadge"
```

---

### Task 1.3: Create Icon Sidebar

**Files:**
- Create: `frontend/src/components/layout/IconSidebar.tsx`
- Create: `frontend/src/components/layout/BottomNav.tsx`
- Create: `frontend/src/components/layout/StatusBar.tsx`
- Test: `frontend/src/components/layout/__tests__/IconSidebar.test.tsx`

- [ ] **Step 1: Write test for IconSidebar**

Test: renders logo, 3 nav items + settings + theme toggle, highlights active route, shows badge, expands on hover (CSS class check).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/components/layout/__tests__/IconSidebar.test.tsx`

- [ ] **Step 3: Implement IconSidebar**

Key specs from brand guideline:
- 60px collapsed, 220px on hover (CSS transition, no JS state)
- Logo: 36px gradient square with "S"
- Version text: fades in on hover
- Nav items: icon (24px) + label (13px, fades on hover)
- Active: accent color + 3px left bar
- Badge: warning pill on Activity item
- Separator line between main nav and bottom items
- Bottom: Settings + ThemeToggle pushed via `mt-auto`
- Uses `NavLink` from react-router for active state detection
- `aria-label` on nav items, `aria-current="page"` on active

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Implement BottomNav (mobile)**

4 items: Dashboard, Library, Activity, Settings. Shown only `≤768px`. Uses same route detection as IconSidebar.

- [ ] **Step 6: Implement StatusBar**

Fixed bottom bar: system status dot, "Automation: active/paused", version, next scan timer. Reads from existing `useHealth()` and `useScannerStatus()` hooks.

- [ ] **Step 7: Run all layout tests**

Run: `cd frontend && npm run test -- --run src/components/layout/__tests__/`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/layout/
git commit -m "feat(ui): add IconSidebar, BottomNav, StatusBar layout components"
```

---

### Task 1.4: Wire New Layout into App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Replace Sidebar with IconSidebar in layout**

Update the app shell to use `IconSidebar` + `StatusBar`. Keep all existing routes initially — we'll consolidate routes in later phases.

```tsx
// Replace <Sidebar /> with <IconSidebar />
// Add <StatusBar /> before closing </div>
// Add <BottomNav /> for mobile
// Adjust main content margin: ml-[60px]
```

- [ ] **Step 2: Verify app renders with new sidebar**

Run: `cd frontend && npm run dev:frontend`
Manual check: sidebar visible, navigation works, all existing pages still accessible.

- [ ] **Step 3: Run full test suite**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(ui): wire IconSidebar and StatusBar into app layout"
```

---

### Task 1.5: Create PageHeader Component

**Files:**
- Create: `frontend/src/components/layout/PageHeader.tsx`

- [ ] **Step 1: Write test**

Test: renders title, optional subtitle, optional breadcrumb, optional action buttons slot.

- [ ] **Step 2: Implement PageHeader**

Reusable component combining breadcrumb + h1 + subtitle + right-aligned action slot. Used by every page.

- [ ] **Step 3: Run test, commit**

```bash
git commit -m "feat(ui): add PageHeader component with breadcrumb support"
```

---

## Phase 2: Dashboard Redesign

### Task 2.1: Create Automation Banner

**Files:**
- Create: `frontend/src/components/dashboard/AutomationBanner.tsx`
- Test: `frontend/src/components/dashboard/__tests__/AutomationBanner.test.tsx`

- [ ] **Step 1: Write test**

Test: renders status dot (green=running, gray=paused), title, stats (success rate, today count, needs attention), Pause/Run Now buttons, calls mutation on button click.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement AutomationBanner**

Uses `useScannerStatus()`, `useStats()`, `useWantedSummary()` hooks. Pulsing green dot when automation active.

- [ ] **Step 4: Run test, verify pass**
- [ ] **Step 5: Commit**

---

### Task 2.2: Create HeroStats Component

**Files:**
- Create: `frontend/src/components/dashboard/HeroStats.tsx`
- Test: `frontend/src/components/dashboard/__tests__/HeroStats.test.tsx`

- [ ] **Step 1: Write test**

Test: renders 4 stat cards (Subtitles total, Missing, Quality avg, Low Score), shows delta badges, correct colors.

- [ ] **Step 2: Implement HeroStats**

4-column grid using `useStats()` and `useWantedSummary()`. Each card: label (micro uppercase), value (stat-value size), delta badge, sub-text.

- [ ] **Step 3: Run test, commit**

---

### Task 2.3: Create NeedsAttentionCard

**Files:**
- Create: `frontend/src/components/dashboard/NeedsAttentionCard.tsx`

- [ ] **Step 1: Write test**

Test: renders warning left-border, items with avatar+title+reason, contextual action buttons per item type (no match → Manual Search/Skip, low score → Find Better/Accept, provider error → Retry/Other Provider), "View All" link navigates to Activity.

- [ ] **Step 2: Implement NeedsAttentionCard**

Uses `useWantedItems()` filtered to failed/low-score items. Maps issue type to appropriate action buttons. Limited to top 3-5 items with "View All" link to `/activity`.

- [ ] **Step 3: Run test, commit**

---

### Task 2.4: Integrate New Dashboard Components

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add AutomationBanner above widget grid**
- [ ] **Step 2: Add HeroStats below banner**
- [ ] **Step 3: Add NeedsAttentionCard below hero stats**
- [ ] **Step 4: Keep existing widget grid below**

The existing `DashboardGrid` with all 10 widgets stays. New components are added above it.

- [ ] **Step 5: Run full test suite**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(ui): redesigned dashboard with automation banner, hero stats, needs attention"
```

---

## Phase 3: Library Redesign

### Task 3.1: Enhance Library Page

**Files:**
- Modify: `frontend/src/pages/Library.tsx`
- Create: `frontend/src/components/library/LibraryCard.tsx` (replaces LibraryGridCard)

- [ ] **Step 1: Replace filter dropdowns with FilterChips**

Swap existing status/profile filter dropdowns with the `FilterChips` component. Chips: All, Missing Subs, Low Score, Anime, Movies, Complete.

- [ ] **Step 2: Create LibraryCard with score badge**

New grid card showing:
- Poster (or placeholder icon)
- Score indicator badge (bottom-left of poster, color-coded)
- Missing count badge (top-right, warning color)
- Title (truncated)
- Meta line (season, episode count, completion checkmark)

- [ ] **Step 3: Update grid/table toggle styling**

Use new radius and spacing tokens. Grid card hover: `translateY(-2px)` + accent border.

- [ ] **Step 4: Run tests, commit**

---

### Task 3.2: Enhance Series Detail Page

**Files:**
- Modify: `frontend/src/pages/SeriesDetail.tsx`
- Create: `frontend/src/components/library/SeasonSummaryBar.tsx`
- Create: `frontend/src/components/library/EpisodeRow.tsx`

- [ ] **Step 1: Add Breadcrumb navigation**

Add `<Breadcrumb items={[{label:'Library', href:'/library'}, {label: series.title}]} />` at top.

- [ ] **Step 2: Create series hero section**

Poster + info layout: poster left (180px), info right with title, year, meta-tags, stat boxes (Episodes, With Subs, Missing, Low Score), action buttons.

- [ ] **Step 3: Implement SeasonSummaryBar**

Color-coded progress bar per season: green (OK), orange (low score), red (missing). Shows counts next to bar.

- [ ] **Step 4: Implement EpisodeRow**

Grid row: episode number, title+filename, format badge, provider, score badge (ScoreBadge component), action buttons. Color-coded left border: red=missing, orange=low score.

- [ ] **Step 5: Integrate into SeriesDetail**

Replace current episode list rendering with `SeasonSummaryBar` + `EpisodeRow` components. Keep ALL existing modals (editor, player, sync, comparison, etc.) — they open from the same action buttons.

- [ ] **Step 6: Run tests, commit**

```bash
git commit -m "feat(ui): enhanced series detail with hero section, season summary, score-colored episodes"
```

---

## Phase 4: Activity (Unified Page)

### Task 4.1: Create ActivityPage

**Files:**
- Create: `frontend/src/pages/ActivityPage.tsx`
- Create: `frontend/src/components/activity/ActivityTabs.tsx`
- Create: `frontend/src/components/activity/NeedsAttentionTab.tsx`
- Create: `frontend/src/components/activity/InProgressTab.tsx`

- [ ] **Step 1: Write test for ActivityPage**

Test: renders PillTabs with 5 tabs (Needs Attention, Wanted, In Progress, Completed, Blacklist), each with count badge. Tab switching shows correct content.

- [ ] **Step 2: Implement ActivityPage shell**

```tsx
// ActivityPage.tsx
const TABS = [
  { id: 'attention', label: 'Needs Attention', count: attentionCount },
  { id: 'wanted', label: 'Wanted', count: wantedCount },
  { id: 'progress', label: 'In Progress', count: progressCount },
  { id: 'completed', label: 'Completed' },
  { id: 'blacklist', label: 'Blacklist', count: blacklistCount },
];
```

- [ ] **Step 3: Implement NeedsAttentionTab**

Table with columns: checkbox, Title, Issue (status pill), Attempts, Last Tried, Actions. FilterChips: All, No Match, Low Score, Provider Error. Batch action bar at bottom.

Uses `useWantedItems()` filtered to failed items.

- [ ] **Step 4: Wire Wanted tab**

Import existing `VirtualWantedTable` and `InteractiveSearchModal` from old Wanted page. Render them inside the "Wanted" tab. No functionality changes.

- [ ] **Step 5: Wire In Progress tab**

Import existing job queue rendering from old Queue page. Show active/queued jobs with progress bars. Uses `useJobs()`.

- [ ] **Step 6: Wire Completed tab**

Import existing history table from old History page. Keep all filters, batch actions, subtitle editor modal. Uses `useHistory()`.

- [ ] **Step 7: Wire Blacklist tab**

Import existing blacklist table from old Blacklist page. Keep pagination, delete, clear all. Uses `useBlacklist()`.

- [ ] **Step 8: Add "Auto-Fix All" button in page actions**

Button triggers batch retry of all attention items.

- [ ] **Step 9: Run tests, commit**

```bash
git commit -m "feat(ui): unified Activity page with 5 tabs replacing 4 separate pages"
```

---

### Task 4.2: Update Routes

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add `/activity` route pointing to ActivityPage**
- [ ] **Step 2: Add redirect routes from old URLs**

```tsx
<Route path="/wanted" element={<Navigate to="/activity?tab=wanted" replace />} />
<Route path="/queue" element={<Navigate to="/activity?tab=progress" replace />} />
<Route path="/history" element={<Navigate to="/activity?tab=completed" replace />} />
<Route path="/blacklist" element={<Navigate to="/activity?tab=blacklist" replace />} />
```

- [ ] **Step 3: Run full test suite, commit**

```bash
git commit -m "feat(ui): add activity route with redirects from old page URLs"
```

---

## Phase 5: Settings (Complete Rebuild)

> **Dependencies:** Tasks 5.1 and 5.2 must complete first (overview + detail layout). Tasks 5.3–5.10 (individual category pages) are independent and can run in parallel. Task 5.11 (routing) depends on all prior tasks. Task 5.12 (search) depends on 5.1.

> **Strategy for existing tab files:** Reuse existing tab component internals (form fields, hooks, logic) inside new settings pages. Extract sections as needed. Old tab files are NOT deleted until Phase 6 (Task 6.2) after full verification.

### Task 5.1: Create Settings Overview (Card Grid)

**Files:**
- Create: `frontend/src/pages/Settings/SettingsOverview.tsx`
- Create: `frontend/src/components/settings/SettingsGrid.tsx`
- Create: `frontend/src/components/settings/FeatureAddon.tsx`

- [ ] **Step 1: Write test for SettingsGrid**

Test: renders 8 category cards with icon, title, description, count. Clicking card navigates to `/settings/:category`. Translation card disabled when feature off.

- [ ] **Step 2: Implement SettingsGrid**

8 cards as defined in brand guideline. Each card: icon box, title, description, top-right count/tag. Click → `navigate('/settings/' + category.id)`.

- [ ] **Step 3: Implement FeatureAddon**

Reusable toggle card for optional features. Used for Translation toggle inside General settings detail page.

- [ ] **Step 4: Implement SettingsOverview**

Page shell with PageHeader ("Settings") + SettingsSearch + SettingsGrid.

- [ ] **Step 5: Run tests, commit**

---

### Task 5.2: Create Settings Detail Layout

**Files:**
- Create: `frontend/src/components/settings/SettingsDetailLayout.tsx`
- Create: `frontend/src/components/settings/FormGroup.tsx`
- Create: `frontend/src/components/settings/SettingsSection.tsx`
- Create: `frontend/src/components/settings/AutoSaveToast.tsx`

- [ ] **Step 1: Implement SettingsDetailLayout**

Wraps each settings detail page with: Breadcrumb (Settings / Category), PageHeader (title + subtitle), max-width container (780px). Provides auto-save context.

- [ ] **Step 2: Implement FormGroup**

Label group (left, max-width 320px): label + hint text. Control group (right, min-width 260px): input/select/toggle. Separated by subtle bottom border.

- [ ] **Step 3: Implement SettingsSection**

Card with icon + title + description header. Contains FormGroup children. Has optional "Advanced" expandable section.

- [ ] **Step 4: Implement AutoSaveToast**

Fixed bottom-right toast: "Setting saved [Undo]". Triggered by `useUpdateConfig()` mutation success. Auto-dismiss after 3s. Undo reverts to previous value.

- [ ] **Step 5: Run tests, commit**

---

### Task 5.3: Create GeneralSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/GeneralSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx`

- [ ] **Step 1: Write test for GeneralSettings**

```tsx
describe('GeneralSettings', () => {
  it('renders Interface section with language selects', () => { /* ... */ });
  it('renders Paths & Server section with media path and port', () => { /* ... */ });
  it('renders Logging section with log level select and toggle', () => { /* ... */ });
  it('renders Translation feature addon toggle', () => { /* ... */ });
  it('calls useUpdateConfig when a setting changes', () => { /* ... */ });
  it('shows advanced fields when expanded', () => { /* ... */ });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- --run src/pages/Settings/__tests__/GeneralSettings.test.tsx`

- [ ] **Step 3: Create page shell with SettingsDetailLayout + breadcrumb**

Wire `<SettingsDetailLayout title="General" subtitle="Language, paths, logging, and optional features">` with breadcrumb back to `/settings`.

- [ ] **Step 4: Add Section 1 — Interface**

Using SettingsSection + FormGroup components:
- Language (select: German/English)
- Source Language (language-select)
- Target Language (language-select)
- HI preference (select: include/prefer/exclude/only)
- Forced preference (select)

- [ ] **Step 5: Add Section 2 — Paths & Server**

- Media Path (text input)
- Port (number input)
- Advanced (expandable): Workers, Base URL, DB Path

- [ ] **Step 6: Add Section 3 — Logging**

- Log Level (select: INFO/DEBUG/WARNING/ERROR)
- Log to File (toggle)

- [ ] **Step 7: Add Feature Addon — Translation toggle**

FeatureAddon card at bottom. Toggle stores `translation_enabled` via `useUpdateConfig()`. When enabled, Translation card on settings overview becomes active.

- [ ] **Step 8: Wire all fields to useConfig() and useUpdateConfig()**

Auto-save with debounce. Each field change triggers `useUpdateConfig()` which shows AutoSaveToast.

- [ ] **Step 9: Run test to verify it passes**

Run: `cd frontend && npm run test -- --run src/pages/Settings/__tests__/GeneralSettings.test.tsx`

- [ ] **Step 10: Commit**

```bash
git add frontend/src/pages/Settings/GeneralSettings.tsx frontend/src/pages/Settings/__tests__/GeneralSettings.test.tsx
git commit -m "feat(ui): add General settings detail page with translation feature toggle"
```

---

### Task 5.4: Create ConnectionsSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/ConnectionsSettings.tsx`
- Create: `frontend/src/components/settings/ConnectionCard.tsx`
- Test: `frontend/src/components/settings/__tests__/ConnectionCard.test.tsx`
- Test: `frontend/src/pages/Settings/__tests__/ConnectionsSettings.test.tsx`

- [ ] **Step 1: Write test for ConnectionCard**

Test: renders service name, status badge, URL, Test/Edit buttons, expands on edit click, calls test mutation on Test click.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement ConnectionCard**

Card showing: service icon/abbreviation, service name, status badge (Connected/Not Configured/Error), URL, item count, Test button, Edit button. Expandable for editing fields (URL, API key, path mappings).

- [ ] **Step 4: Run test, verify pass**
- [ ] **Step 5: Write test for ConnectionsSettings**

Test: renders Sonarr card, Radarr card, Media Server cards, API Keys section, Add Connection button.

- [ ] **Step 6: Implement ConnectionsSettings**

Shows connection cards for:
- Sonarr (from existing MediaServersTab sonarr config)
- Radarr (from existing MediaServersTab radarr config)
- Media Servers (from existing MediaServersTab — Jellyfin/Plex/Kodi instances)
- API Keys section (from existing ApiKeysTab)
- "+ Add Connection" button

Uses existing hooks: `useConfig()`, `useMediaServerInstances()`, `useTestMediaServer()`, `useApiKeys()`.

- [ ] **Step 7: Run tests, verify pass**
- [ ] **Step 8: Commit**

```bash
git commit -m "feat(ui): add Connections settings page with service connection cards"
```

---

### Task 5.5: Create SubtitlesSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/SubtitlesSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/SubtitlesSettings.test.tsx`

- [ ] **Step 1: Write test for SubtitlesSettings**

Test: renders all 6 sections, scoring fields use correct hooks, advanced sections start collapsed.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Create page shell with Scoring section**

Min score, scoring weights, provider modifiers, presets (reuse logic from EventsTab/ScoringTab).

- [ ] **Step 4: Add Format & Tools section**

Default format, conversion, subtitle tools (reuse from AdvancedTab/SubtitleToolsTab).

- [ ] **Step 5: Add Cleanup section**

Dedup, orphaned cleanup (reuse from CleanupTab).

- [ ] **Step 6: Add Embedded Extraction section (advanced)**

Auto-extract, language selection (from wanted settings).

- [ ] **Step 7: Add Language Profiles section (advanced)**

Profile CRUD (reuse from AdvancedTab profiles).

- [ ] **Step 8: Add Fansub Preferences section (advanced)**

Global fansub prefs (reuse from existing modal).

- [ ] **Step 9: Run tests, verify pass**
- [ ] **Step 10: Commit**

```bash
git commit -m "feat(ui): add Subtitles settings page with scoring, format, cleanup, profiles"
```

---

### Task 5.6: Create ProvidersSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/ProvidersSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/ProvidersSettings.test.tsx`

- [ ] **Step 1: Write test for ProvidersSettings**

Test: renders installed provider grid, marketplace section, anti-captcha config, cache clear button.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Implement Installed Providers section**

Reuse existing `ProviderTile` components in a grid layout (from ProvidersTab). Add drag-to-reorder.

- [ ] **Step 4: Implement Marketplace section**

Merge existing `MarketplaceTab` components with Plugins page marketplace. Show "Available" providers and plugins.

- [ ] **Step 5: Add Anti-captcha and Cache sections**

Anti-captcha toggle + API key. Cache clear button (all or per-provider).

- [ ] **Step 6: Run tests, verify pass**
- [ ] **Step 7: Commit**

```bash
git commit -m "feat(ui): add Providers settings page with marketplace and cache management"
```

---

### Task 5.7: Create AutomationSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/AutomationSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/AutomationSettings.test.tsx`

- [ ] **Step 1: Write test for AutomationSettings**

Test: renders all 7 sections, task cards show run/cancel buttons, toggles call useUpdateConfig.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Add Search & Scan section**

Search interval, wanted scan config, anime filters (from old Wanted settings).

- [ ] **Step 4: Add Upgrade Rules section**

Auto-upgrade toggle, min delta, window, prefer ASS (from old Automation tab).

- [ ] **Step 5: Add Provider Re-ranking + Post-Download sections**

Re-ranking config + webhook delay, auto-scan, auto-search, auto-translate toggles.

- [ ] **Step 6: Add Processing Pipeline section**

Reuse `ProcessingPipelineSettings` component. Rules editor + preview.

- [ ] **Step 7: Add Sidecar & Cleanup section**

Auto-cleanup, keep languages, preferred format.

- [ ] **Step 8: Add Scheduled Tasks section**

Task cards with run/cancel/enable (migrate from old Tasks page). Uses `useTasks()`, `useTriggerTask()`, `useCancelTask()`.

- [ ] **Step 9: Run tests, verify pass**
- [ ] **Step 10: Commit**

```bash
git commit -m "feat(ui): add Automation settings page with scheduling, upgrades, processing"
```

---

### Task 5.8: Create TranslationSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/TranslationSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/TranslationSettings.test.tsx`

- [ ] **Step 1: Write test for TranslationSettings**

Test: renders nothing when translation disabled, renders all sections when enabled, backend test button calls hook.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Add conditional gate + page shell**

Check `translation_enabled` from `useConfig()`. If disabled, show a message with link to enable in General settings.

- [ ] **Step 4: Add Translation Backends section**

Reuse backend card logic from existing TranslationTab. Config, test, stats per backend.

- [ ] **Step 5: Add Prompt Presets + Glossary sections**

CRUD list with set-as-default. Glossary: search, add/edit/delete, suggest terms, export TSV.

- [ ] **Step 6: Add Translation Memory + Quality + Auto-Sync sections**

Enable toggles, thresholds, cache management, engine selection.

- [ ] **Step 7: Add Whisper (STT) sub-section**

Reuse WhisperTab backend config (enable, model, device, temperature).

- [ ] **Step 8: Run tests, verify pass**
- [ ] **Step 9: Commit**

```bash
git commit -m "feat(ui): add Translation settings page (conditional on feature toggle)"
```

---

### Task 5.9: Create NotificationsSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/NotificationsSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/NotificationsSettings.test.tsx`

- [ ] **Step 1: Write test for NotificationsSettings**

Test: renders channels section, quiet hours section, history section, template CRUD works.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Add Channels section**

Reuse template CRUD logic from existing NotificationTemplatesTab. Event type filtering, preview.

- [ ] **Step 4: Add Quiet Hours section**

Reuse from existing QuietHoursConfig. Time range CRUD with enable toggle.

- [ ] **Step 5: Add Notification History section**

History log with resend button. Uses `useNotificationHistory()`.

- [ ] **Step 6: Run tests, verify pass**
- [ ] **Step 7: Commit**

```bash
git commit -m "feat(ui): add Notifications settings page with channels, quiet hours, history"
```

---

### Task 5.10: Create SystemSettings Page

**Files:**
- Create: `frontend/src/pages/Settings/SystemSettings.tsx`
- Test: `frontend/src/pages/Settings/__tests__/SystemSettings.test.tsx`

- [ ] **Step 1: Write test for SystemSettings**

Test: renders all 7 sections, backup create button calls mutation, log viewer shows log entries.

- [ ] **Step 2: Run test, verify fail**
- [ ] **Step 3: Add Security section**

Auth settings, CORS, rate limiting (reuse from SecurityTab).

- [ ] **Step 4: Add Backup & Restore section**

Full backup CRUD (reuse from AdvancedTab/BackupTab). Create, download, restore, delete.

- [ ] **Step 5: Add Events & Hooks section**

Hook CRUD, webhook config (reuse from EventsTab hooks section).

- [ ] **Step 6: Add Log Viewer section**

Inline log viewer with virtual scrolling, level filter, search (migrate from old Logs page). Uses `useLogs()`.

- [ ] **Step 7: Add Integrations + Migration + Statistics Export sections**

Integrations (from IntegrationsTab), migration tools (from MigrationTab), chart export (from old Statistics page).

- [ ] **Step 8: Run tests, verify pass**
- [ ] **Step 9: Commit**

```bash
git commit -m "feat(ui): add System settings page with security, backup, logs, integrations"
```

---

### Task 5.11: Wire Settings Routes

**Files:**
- Modify: `frontend/src/pages/Settings/index.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Update Settings index as router**

```tsx
// Settings/index.tsx
import { Routes, Route } from 'react-router-dom';
import { SettingsOverview } from './SettingsOverview';
import { GeneralSettings } from './GeneralSettings';
// ... other imports

export function SettingsPage() {
  return (
    <Routes>
      <Route index element={<SettingsOverview />} />
      <Route path="general" element={<GeneralSettings />} />
      <Route path="connections" element={<ConnectionsSettings />} />
      <Route path="subtitles" element={<SubtitlesSettings />} />
      <Route path="providers" element={<ProvidersSettings />} />
      <Route path="automation" element={<AutomationSettings />} />
      <Route path="translation" element={<TranslationSettings />} />
      <Route path="notifications" element={<NotificationsSettings />} />
      <Route path="system" element={<SystemSettings />} />
    </Routes>
  );
}
```

- [ ] **Step 2: Update App.tsx settings route**

Change `/settings` route to use `path="/settings/*"` for nested routing.

- [ ] **Step 3: Add redirects from old page URLs**

```tsx
<Route path="/statistics" element={<Navigate to="/settings/system" replace />} />
<Route path="/tasks" element={<Navigate to="/settings/automation" replace />} />
<Route path="/logs" element={<Navigate to="/settings/system" replace />} />
<Route path="/plugins" element={<Navigate to="/settings/providers" replace />} />
```

- [ ] **Step 4: Run full test suite**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(ui): complete settings rebuild — 8 category pages with card grid overview"
```

---

### Task 5.12: Implement Settings Search

**Files:**
- Create: `frontend/src/components/settings/SettingsSearch.tsx`
- Create: `frontend/src/components/settings/settingsRegistry.ts`
- Test: `frontend/src/components/settings/__tests__/SettingsSearch.test.tsx`

- [ ] **Step 1: Write test for SettingsSearch**

```tsx
describe('SettingsSearch', () => {
  it('renders search input with placeholder', () => { /* ... */ });
  it('filters results on input', () => { /* ... */ });
  it('shows matching settings with category label', () => { /* ... */ });
  it('navigates to settings page on result click', () => { /* ... */ });
  it('shows "no results" for unmatched query', () => { /* ... */ });
  it('debounces input (no results for <150ms input)', () => { /* ... */ });
});
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Create settings registry**

Static registry of all setting fields: `{ id, label, description, category, section }[]`. Used for search matching.

- [ ] **Step 4: Implement SettingsSearch**

Search input at top of settings overview. Searches across all settings labels/descriptions via registry. Results link directly to `/settings/:category` with section anchor. Filters on keypress with debounce (150ms).

- [ ] **Step 5: Run tests, verify pass**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat(ui): add global settings search with registry and debounced filtering"
```

---

## Phase 6: Polish & Cleanup

### Task 6.1: Update i18n Keys

**Files:**
- Modify: `frontend/src/i18n/locales/en/common.json`
- Modify: `frontend/src/i18n/locales/en/settings.json`
- Modify: `frontend/src/i18n/locales/en/activity.json`
- Modify: `frontend/src/i18n/locales/de/common.json`
- Modify: `frontend/src/i18n/locales/de/settings.json`
- Modify: `frontend/src/i18n/locales/de/activity.json`

- [ ] **Step 1: Add new translation keys for all new UI elements**

New keys needed:
- Sidebar labels (dashboard, library, activity, settings)
- Activity tab labels (needs_attention, wanted, in_progress, completed, blacklist)
- Settings category titles and descriptions (all 8)
- Settings section headers
- Automation banner text
- Hero stat labels
- Status bar text
- Breadcrumb labels
- Toast messages

- [ ] **Step 2: Verify no missing translation keys**

Run: grep for hardcoded English strings in new components.

- [ ] **Step 3: Commit**

---

### Task 6.2: Remove Old Pages

**Files:**
- Delete: `frontend/src/pages/Wanted.tsx`
- Delete: `frontend/src/pages/Queue.tsx`
- Delete: `frontend/src/pages/History.tsx`
- Delete: `frontend/src/pages/Blacklist.tsx`
- Delete: `frontend/src/pages/Statistics.tsx`
- Delete: `frontend/src/pages/Tasks.tsx`
- Delete: `frontend/src/pages/Logs.tsx`
- Delete: `frontend/src/pages/Plugins.tsx`
- Modify: `frontend/src/App.tsx` (remove old route imports)

- [ ] **Step 1: Verify all features from old pages exist in new locations**

Manual checklist: go through every feature from the migration map and confirm it works in the new location.

- [ ] **Step 2: Remove old page files**

Only remove after full verification. Keep redirect routes in App.tsx.

- [ ] **Step 3: Remove old Sidebar component**

Delete `frontend/src/components/layout/Sidebar.tsx` (replaced by IconSidebar).

- [ ] **Step 4: Run full test suite**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run`

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(ui): remove old pages replaced by unified Activity and Settings"
```

---

### Task 6.3: Responsive & Accessibility Audit

**Files:**
- Modify: Various components as needed

- [ ] **Step 1: Test mobile layout (375px)**

Verify: bottom nav visible, sidebar hidden, grids stack, episode rows simplified.

- [ ] **Step 2: Test tablet layout (768px)**

Verify: sidebar icon-only, 2-column grids, readable content.

- [ ] **Step 3: Keyboard navigation audit**

Tab through all interactive elements. Verify: focus rings visible, tab order logical, Escape closes modals, Ctrl+K opens search.

- [ ] **Step 4: Screen reader check**

Verify: all icon buttons have aria-labels, nav items have aria-current, tables have proper headers, live regions for toasts.

- [ ] **Step 5: Reduced motion check**

Enable `prefers-reduced-motion` and verify all animations reduce to opacity-only.

- [ ] **Step 6: Fix any issues found**
- [ ] **Step 7: Commit**

---

### Task 6.4: Animation & Transitions

**Files:**
- Modify: `frontend/src/index.css`
- Modify: Various components

- [ ] **Step 1: Add page transition animation**

Fade-in on route change (200ms). Use React Router's transition support or a simple wrapper.

- [ ] **Step 2: Add sidebar hover animation**

CSS transition on width: 300ms ease-out. Label opacity transition: 150ms.

- [ ] **Step 3: Add card hover effects**

translateY(-2px) + border-color change on hoverable cards (library cards, settings cards).

- [ ] **Step 4: Add accordion animations**

Smooth height + opacity for advanced sections in settings. 250ms duration.

- [ ] **Step 5: Add skeleton loading states**

Ensure skeleton screens show for all async-loaded content. Use existing skeleton components.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(ui): add page transitions, hover effects, accordion animations"
```

---

### Task 6.5: Final Verification

- [ ] **Step 1: Run pre-PR checks**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run test -- --run
```

- [ ] **Step 2: Visual regression on 4 breakpoints**

375px, 768px, 1024px, 1440px — screenshot all pages in dark + light mode.

- [ ] **Step 3: Verify all features from migration map work**

Go through every row in the Feature Migration Map table and verify functionality.

- [ ] **Step 4: Test dark/light mode toggle**

Both themes consistent, borders visible, contrast adequate.

- [ ] **Step 5: Final commit**

```bash
git commit -m "chore(ui): frontend redesign complete — all features verified"
```

---

## Verification Checklist

- [ ] All 16 original pages' features accessible in new 4-page layout
- [ ] All 18 settings tabs' content present in 8 category pages
- [ ] Translation toggle in General settings controls Translation card visibility
- [ ] Automation banner shows real-time status from API
- [ ] Needs Attention card shows correct items with contextual actions
- [ ] Activity page tabs switch correctly with badge counts
- [ ] Series detail shows season summary bar and score-coded episodes
- [ ] All modals (editor, player, sync, comparison, etc.) still open and function
- [ ] Settings auto-save works with undo toast
- [ ] Settings search finds settings across categories
- [ ] Old URLs redirect to new locations
- [ ] Mobile bottom nav works
- [ ] Keyboard navigation (Tab, Escape, Ctrl+K) works
- [ ] Dark/light mode both render correctly
- [ ] No TypeScript errors, no lint errors, all tests pass
- [ ] i18n keys exist for EN and DE for all new UI text
