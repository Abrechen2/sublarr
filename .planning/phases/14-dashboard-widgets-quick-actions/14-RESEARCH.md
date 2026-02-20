# Phase 14: Dashboard Widgets + Quick-Actions - Research

**Researched:** 2026-02-19
**Domain:** React drag-and-drop grid layouts, keyboard shortcuts, dashboard widget systems
**Confidence:** HIGH

## Summary

Phase 14 transforms the existing static Dashboard page into a customizable widget-based layout with drag-and-drop rearrangement, resizable widgets, visibility toggling, and adds a Quick-Actions toolbar with keyboard shortcuts across all pages.

The existing Dashboard (`frontend/src/pages/Dashboard.tsx`, ~445 lines) already renders six distinct visual sections (StatCards, Quick Actions, Service Status, Provider Health, Health Quality widget, Recent Activity) which map naturally to widget components. The codebase already uses Zustand (v5) for cross-page state management and TanStack Query (v5) for data fetching, providing all the primitives needed for widget data management and layout persistence.

**react-grid-layout v2.2.2** (released December 2025, full TypeScript rewrite with hooks API) is the clear choice for the drag-and-drop grid. It provides `useContainerWidth`, responsive breakpoints, and layout persistence out of the box. For keyboard shortcuts, **react-hotkeys-hook v5.2.4** provides scoped hotkeys with a clean hook API, and the project already has a keyboard shortcut pattern in App.tsx (Ctrl+K for search). The FAB (Floating Action Button) with expandable quick-actions is a pure Tailwind CSS + React component -- no library needed.

**Primary recommendation:** Use react-grid-layout v2 with Responsive component + zustand persist for layout state + react-hotkeys-hook for keyboard shortcuts. Build the FAB as a custom component using existing design tokens.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| react-grid-layout | ^2.2.2 | Drag-and-drop resizable grid layout | Only mature React grid layout library; v2 is full TypeScript rewrite with hooks API; 21.5k GitHub stars; ~1M weekly npm downloads; peer dep `react >= 16.3.0` so works with React 19 |
| react-hotkeys-hook | ^5.2.4 | Keyboard shortcuts | Most popular React keyboard shortcuts library; 15.7k GitHub stars; TypeScript native; scoped hotkeys; v5.2.4 released Feb 2026 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zustand (persist middleware) | ^5.0.11 (already installed) | Persist widget layout/visibility to localStorage | Store user's dashboard layout preferences across sessions |
| lucide-react | ^0.564.0 (already installed) | Widget icons and FAB icons | Icon system for widget headers and quick-action buttons |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| react-grid-layout | @dnd-kit/core | dnd-kit has more weekly downloads (4.78M vs 1M) and is more flexible, but requires building grid/resize logic from scratch. RGL is purpose-built for dashboard grids with resize+drag+responsive built in. |
| react-grid-layout | gridstack.js | JavaScript-first library with clunky React integration; not TypeScript native; less React-idiomatic |
| react-hotkeys-hook | tinykeys | tinykeys is smaller (~650B) but has no React-specific features (scopes, ref-based focus, HotkeysProvider); requires manual cleanup in useEffect |
| Custom FAB | @syncfusion/react-fab | Heavy UI library dependency for a simple component; not justified for a single button |

**Installation:**
```bash
cd frontend && npm install react-grid-layout react-hotkeys-hook
```

Note: `@types/react-grid-layout` is NOT needed -- v2 ships with built-in TypeScript types.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── components/
│   ├── dashboard/
│   │   ├── DashboardGrid.tsx           # Responsive grid wrapper with useContainerWidth
│   │   ├── WidgetWrapper.tsx           # Generic widget chrome (header, drag handle, resize, visibility)
│   │   ├── WidgetSettingsModal.tsx      # Toggle widget visibility, reset layout
│   │   └── widgets/
│   │       ├── StatCardsWidget.tsx      # Ollama status, wanted, translated, queue
│   │       ├── QuickActionsWidget.tsx   # Scan library, search wanted buttons
│   │       ├── ServiceStatusWidget.tsx  # Service health dots
│   │       ├── ProviderHealthWidget.tsx # Provider status list
│   │       ├── QualityWidget.tsx        # Subtitle quality sparkline (existing HealthDashboardWidget)
│   │       ├── RecentActivityWidget.tsx # Activity feed with job list
│   │       ├── TranslationStatsWidget.tsx # Total/format/system stats
│   │       └── WantedSummaryWidget.tsx  # Wanted items breakdown by status
│   ├── quick-actions/
│   │   ├── QuickActionsFAB.tsx         # Floating action button with expandable menu
│   │   └── KeyboardShortcutsModal.tsx  # "?" shortcut to show all shortcuts
│   └── ...
├── stores/
│   ├── selectionStore.ts               # (existing)
│   ├── dashboardStore.ts               # Widget layout, visibility, persisted via zustand/persist
│   └── quickActionsStore.ts            # Quick-action scopes and context
├── hooks/
│   ├── useApi.ts                       # (existing)
│   ├── useKeyboardShortcuts.ts         # App-wide keyboard shortcut registration
│   └── useDashboardLayout.ts           # Layout persistence + default layouts
└── ...
```

### Pattern 1: Widget Registry Pattern
**What:** Each widget type is registered in a central registry with metadata (id, title, icon, default size, min size, component). The grid layout references widgets by ID only.
**When to use:** When you need a dynamic, extensible set of widget types
**Example:**
```typescript
// Source: Custom pattern for this codebase
interface WidgetDefinition {
  readonly id: string
  readonly titleKey: string          // i18n key
  readonly icon: LucideIcon
  readonly defaultLayout: { w: number; h: number; minW?: number; minH?: number }
  readonly component: React.LazyExoticComponent<React.ComponentType>
}

const WIDGET_REGISTRY: readonly WidgetDefinition[] = [
  {
    id: 'stat-cards',
    titleKey: 'dashboard:widgets.stat_cards',
    icon: BarChart3,
    defaultLayout: { w: 12, h: 2, minW: 6, minH: 2 },
    component: lazy(() => import('./widgets/StatCardsWidget')),
  },
  // ... 7 more widgets
] as const

type WidgetId = typeof WIDGET_REGISTRY[number]['id']
```

### Pattern 2: Zustand Persist for Dashboard Layout
**What:** Store the grid layout (positions, sizes) and widget visibility in a Zustand store with `persist` middleware, backed by localStorage.
**When to use:** When layout state must survive browser refreshes without backend API calls.
**Example:**
```typescript
// Source: zustand docs - https://zustand.docs.pmnd.rs/middlewares/persist
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Layout } from 'react-grid-layout'

interface DashboardState {
  layouts: Record<string, Layout[]>      // breakpoint -> Layout[]
  hiddenWidgets: Set<string>             // widget IDs that are hidden
  setLayouts: (breakpoint: string, layout: Layout[]) => void
  toggleWidget: (widgetId: string) => void
  resetToDefault: () => void
}

export const useDashboardStore = create<DashboardState>()(
  persist(
    (set) => ({
      layouts: {},
      hiddenWidgets: new Set(),
      setLayouts: (breakpoint, layout) =>
        set((state) => ({
          layouts: { ...state.layouts, [breakpoint]: layout },
        })),
      toggleWidget: (widgetId) =>
        set((state) => {
          const hidden = new Set(state.hiddenWidgets)
          if (hidden.has(widgetId)) {
            hidden.delete(widgetId)
          } else {
            hidden.add(widgetId)
          }
          return { hiddenWidgets: hidden }
        }),
      resetToDefault: () => set({ layouts: {}, hiddenWidgets: new Set() }),
    }),
    {
      name: 'sublarr-dashboard',
      // Custom serializer for Set
      storage: {
        getItem: (name) => {
          const str = localStorage.getItem(name)
          if (!str) return null
          const parsed = JSON.parse(str)
          if (parsed?.state?.hiddenWidgets) {
            parsed.state.hiddenWidgets = new Set(parsed.state.hiddenWidgets)
          }
          return parsed
        },
        setItem: (name, value) => {
          const serializable = {
            ...value,
            state: {
              ...value.state,
              hiddenWidgets: [...value.state.hiddenWidgets],
            },
          }
          localStorage.setItem(name, JSON.stringify(serializable))
        },
        removeItem: (name) => localStorage.removeItem(name),
      },
    }
  )
)
```

### Pattern 3: React-Grid-Layout v2 with Responsive + useContainerWidth
**What:** Use the v2 hooks API for container measurement and responsive breakpoints.
**When to use:** For all dashboard grid rendering.
**Example:**
```typescript
// Source: react-grid-layout v2 CHANGELOG + README
import { Responsive, useContainerWidth } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

function DashboardGrid() {
  const { width, containerRef, mounted } = useContainerWidth()
  const { layouts, setLayouts } = useDashboardStore()

  const handleLayoutChange = (_currentLayout: Layout[], allLayouts: Layouts) => {
    // allLayouts is Record<string, Layout[]>
    Object.entries(allLayouts).forEach(([bp, layout]) => {
      setLayouts(bp, layout)
    })
  }

  return (
    <div ref={containerRef}>
      {mounted && (
        <Responsive
          width={width}
          layouts={mergedLayouts}
          breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
          cols={{ lg: 12, md: 10, sm: 6, xs: 4, xxs: 2 }}
          rowHeight={60}
          gridConfig={{ margin: [12, 12] }}
          dragConfig={{ handle: '.widget-drag-handle' }}
          resizeConfig={{ handles: ['se'] }}
          onLayoutChange={handleLayoutChange}
        >
          {visibleWidgets.map((widget) => (
            <div key={widget.id}>
              <WidgetWrapper definition={widget}>
                <Suspense fallback={<WidgetSkeleton />}>
                  <widget.component />
                </Suspense>
              </WidgetWrapper>
            </div>
          ))}
        </Responsive>
      )}
    </div>
  )
}
```

### Pattern 4: Context-Specific Quick Actions with Scoped Hotkeys
**What:** Each page registers its own context-specific actions. The FAB shows actions for the current route.
**When to use:** For the quick-actions toolbar requirement (DASH-04).
**Example:**
```typescript
// Source: react-hotkeys-hook docs
import { useHotkeys } from 'react-hotkeys-hook'
import { useLocation } from 'react-router-dom'

// In WantedPage:
useHotkeys('shift+s', () => startBatchSearch(), { description: 'Search all wanted' })
useHotkeys('shift+r', () => refreshWanted(), { description: 'Refresh wanted scan' })

// In SeriesDetailPage:
useHotkeys('shift+e', () => openEditor(), { description: 'Edit subtitle' })
useHotkeys('shift+h', () => runHealthCheck(), { description: 'Run health check' })
```

### Anti-Patterns to Avoid
- **Storing layout in backend config_entries:** Dashboard layout is a purely frontend concern. Using the config API would create unnecessary API calls and slow down layout saves during drag operations. Use localStorage via Zustand persist.
- **Building custom drag-and-drop:** react-grid-layout handles collision detection, compaction, responsive breakpoints, and resize handles. Hand-rolling this is weeks of work for inferior results.
- **One giant Dashboard component:** The current Dashboard.tsx is already ~445 lines. With widgets it would balloon. Extract each widget into its own file with its own data hooks.
- **Global keyboard shortcuts without cleanup:** Always scope shortcuts to components or use react-hotkeys-hook's scope system. Unscoped global listeners leak across routes.
- **Importing RGL CSS directly into components:** Import the two required CSS files (`react-grid-layout/css/styles.css` and `react-resizable/css/styles.css`) once in the entry point or Dashboard page, not in every widget.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Drag-and-drop grid layout | Custom drag/drop with mouse events | react-grid-layout v2 Responsive | Collision detection, compaction, responsive breakpoints, resize handles, touch support, performance optimization -- thousands of edge cases |
| Keyboard shortcut management | Custom keydown listeners (App.tsx pattern) | react-hotkeys-hook v5 | Scope management, modifier keys, sequential hotkeys, form element detection, cleanup, cross-platform $mod support |
| Layout persistence | Manual localStorage.getItem/setItem | zustand persist middleware | Handles serialization, hydration timing, storage abstraction, state merging |
| Container width measurement | Manual ResizeObserver | react-grid-layout useContainerWidth | SSR-safe, debounced, cleanup handled, ref-based |

**Key insight:** Dashboard widget grids are deceptively complex. Collision detection during drag, compaction algorithms, responsive breakpoint transitions, resize handle rendering, bounded movement, and touch support each have dozens of edge cases. react-grid-layout has been solving these problems for 8+ years.

## Common Pitfalls

### Pitfall 1: Missing RGL CSS Imports
**What goes wrong:** Grid items stack vertically, no drag handles appear, resize handles invisible
**Why it happens:** react-grid-layout requires two CSS files that style the grid items and resize handles
**How to avoid:** Import both CSS files in the Dashboard page or entry point:
```typescript
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
```
**Warning signs:** Items not draggable, no visual resize handle in bottom-right corner

### Pitfall 2: Width Prop Required in v2
**What goes wrong:** TypeScript error or runtime crash: "width prop is required"
**Why it happens:** v2 removed automatic width detection from WidthProvider (legacy only); the width prop is now mandatory
**How to avoid:** Always use `useContainerWidth()` hook and pass `width` to the grid
**Warning signs:** Console error about missing width prop

### Pitfall 3: Layout Key Mismatch
**What goes wrong:** Widgets disappear, wrong widget in wrong position, layout resets
**Why it happens:** The `key` prop on child elements must match the `i` field in the layout items array
**How to avoid:** Widget registry IDs should be the source of truth for both the `key` prop and layout `i` field
**Warning signs:** Console warnings about missing keys, widgets not matching their expected positions

### Pitfall 4: Zustand Persist Hydration Timing
**What goes wrong:** Dashboard flashes default layout then jumps to saved layout
**Why it happens:** localStorage hydration is synchronous but React may render before the store is fully hydrated
**How to avoid:** Check `useDashboardStore.persist.hasHydrated()` before rendering the grid, or show a loading skeleton
**Warning signs:** Layout "jumps" on page load

### Pitfall 5: Too Many Re-renders During Drag
**What goes wrong:** Janky drag performance, items lag behind cursor
**Why it happens:** `onLayoutChange` fires on every pixel of movement; if it triggers expensive state updates or re-renders, performance degrades
**How to avoid:** Only persist layout in `onDragStop` and `onResizeStop`, not in `onLayoutChange`. Use `onLayoutChange` only for visual updates.
**Warning signs:** Stuttery drag behavior, high CPU during drag

### Pitfall 6: RGL CSS Conflicts with Tailwind
**What goes wrong:** Grid item styles break, incorrect sizing, margin issues
**Why it happens:** Tailwind's CSS reset (`*, ::before, ::after { box-sizing: border-box; }`) can conflict with RGL's positioning if the grid items have padding/border that isn't accounted for
**How to avoid:** Apply `overflow-hidden` to widget wrapper divs. Keep RGL CSS imported after Tailwind. Test drag/resize immediately after integration.
**Warning signs:** Widgets slightly wrong size, margins look off

### Pitfall 7: Keyboard Shortcuts Firing in Input Fields
**What goes wrong:** Typing "s" in a search box triggers the "search wanted" shortcut
**Why it happens:** Global keyboard handlers capture all keystrokes including form input
**How to avoid:** Use `enableOnFormTags: false` (default in react-hotkeys-hook) and always use modifier keys (Shift+S, not just S) for shortcuts
**Warning signs:** Unexpected actions while typing in inputs

## Code Examples

Verified patterns from official sources:

### Widget Wrapper Component
```typescript
// Custom pattern matching existing Sublarr design system
interface WidgetWrapperProps {
  definition: WidgetDefinition
  children: React.ReactNode
  onRemove?: () => void
}

function WidgetWrapper({ definition, children, onRemove }: WidgetWrapperProps) {
  const { t } = useTranslation('dashboard')
  const Icon = definition.icon

  return (
    <div
      className="h-full flex flex-col rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}
    >
      {/* Header with drag handle */}
      <div
        className="widget-drag-handle flex items-center gap-2 px-4 py-2 cursor-grab active:cursor-grabbing"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <Icon size={14} style={{ color: 'var(--accent)' }} />
        <span
          className="text-xs font-semibold uppercase tracking-wider flex-1"
          style={{ color: 'var(--text-muted)' }}
        >
          {t(definition.titleKey)}
        </span>
        {onRemove && (
          <button
            onClick={onRemove}
            className="p-1 rounded hover:bg-[var(--bg-surface-hover)]"
            style={{ color: 'var(--text-muted)' }}
          >
            <X size={12} />
          </button>
        )}
      </div>
      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        {children}
      </div>
    </div>
  )
}
```

### Floating Action Button
```typescript
// Custom pattern using existing Sublarr design tokens
function QuickActionsFAB() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  const actions = getActionsForRoute(location.pathname)

  useHotkeys('shift+/', () => setOpen((prev) => !prev), {
    description: 'Toggle quick actions',
  })

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse items-end gap-2">
      {/* Expandable action items */}
      {open && actions.map((action, i) => (
        <button
          key={action.id}
          onClick={() => { action.handler(); setOpen(false) }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg shadow-lg text-sm font-medium transition-all"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            animation: `fadeSlideUp 0.2s ease-out ${i * 0.05}s both`,
          }}
        >
          <action.icon size={16} style={{ color: 'var(--accent)' }} />
          <span>{action.label}</span>
          {action.shortcut && (
            <kbd
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {action.shortcut}
            </kbd>
          )}
        </button>
      ))}

      {/* Main FAB button */}
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all duration-200"
        style={{
          backgroundColor: 'var(--accent)',
          color: '#fff',
          transform: open ? 'rotate(45deg)' : 'rotate(0deg)',
        }}
      >
        <Plus size={24} />
      </button>
    </div>
  )
}
```

### Keyboard Shortcuts Registration
```typescript
// Source: react-hotkeys-hook docs + custom pattern
import { useHotkeys } from 'react-hotkeys-hook'

// App-level shortcuts (registered in App.tsx or a global hook)
function useGlobalShortcuts() {
  const navigate = useNavigate()

  // Navigation shortcuts
  useHotkeys('g then d', () => navigate('/'), { description: 'Go to Dashboard' })
  useHotkeys('g then l', () => navigate('/library'), { description: 'Go to Library' })
  useHotkeys('g then w', () => navigate('/wanted'), { description: 'Go to Wanted' })
  useHotkeys('g then s', () => navigate('/settings'), { description: 'Go to Settings' })

  // Help
  useHotkeys('shift+/', () => openShortcutsModal(), { description: 'Show keyboard shortcuts' })
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| react-grid-layout v1 (JavaScript, class components, WidthProvider HOC) | v2 (TypeScript, hooks, useContainerWidth) | Dec 2025 | Full TypeScript, no @types needed, composable config, tree-shakeable |
| react-beautiful-dnd | @hello-pangea/dnd or @dnd-kit | 2024 | react-beautiful-dnd is deprecated; but neither replacement has built-in grid resize |
| Manual keydown listeners | react-hotkeys-hook v5 | 2024 | Scoped shortcuts, form element handling, sequential keys, TypeScript native |
| WidthProvider HOC in RGL | useContainerWidth hook | Dec 2025 (v2) | No HOC wrapping, simpler component tree, SSR compatible |
| `data-grid` prop on children | Explicit `layout` prop array | Dec 2025 (v2) | `data-grid` only in legacy mode; v2 requires layout array |

**Deprecated/outdated:**
- react-beautiful-dnd: Unmaintained, not suitable for grid layouts anyway
- react-grid-layout v1 WidthProvider: Still available via `react-grid-layout/legacy` but v2 hooks preferred
- `@types/react-grid-layout`: Not needed with v2, types are built-in

## Open Questions

1. **Backend persistence for dashboard layout (optional)**
   - What we know: localStorage via zustand persist works well for single-user/single-browser. The existing `config_entries` table could store layout JSON if needed.
   - What's unclear: Whether the user wants dashboard layout to sync across devices/browsers
   - Recommendation: Start with localStorage only. If multi-device sync is desired later, add a `dashboard_layout_json` config entry with a "sync to server" button.

2. **Mobile touch support for drag-and-drop**
   - What we know: react-grid-layout supports touch events out of the box
   - What's unclear: Whether the mobile layout should disable drag-and-drop entirely (since it's harder on small screens)
   - Recommendation: Disable drag-and-drop on mobile breakpoints (xs, xxs). Show a single-column stacked layout instead. Allow widget visibility toggle on mobile.

3. **Edit mode vs always-draggable**
   - What we know: Some dashboard systems use an explicit "edit mode" toggle; others always allow dragging via handles
   - What's unclear: User preference
   - Recommendation: Use drag handles (`.widget-drag-handle` class on header) so widgets are always rearrangeable without a mode toggle. Add a "Customize Dashboard" button that opens a modal for widget visibility toggling and layout reset.

## Sources

### Primary (HIGH confidence)
- [react-grid-layout GitHub](https://github.com/react-grid-layout/react-grid-layout) - v2.2.2 README, CHANGELOG, package.json (peer dep: `react >= 16.3.0`)
- [react-grid-layout CHANGELOG](https://github.com/react-grid-layout/react-grid-layout/blob/master/CHANGELOG.md) - v2.0.0 (Dec 9, 2025), v2.1.0 (Dec 14, 2025), v2.2.2 (Dec 30, 2025) release details
- [react-hotkeys-hook GitHub](https://github.com/JohannesKlauss/react-hotkeys-hook) - v5.2.4 (Feb 2, 2026)
- [react-hotkeys-hook API docs](https://react-hotkeys-hook.vercel.app/docs/api/use-hotkeys) - useHotkeys full TypeScript signature
- [zustand persist docs](https://zustand.docs.pmnd.rs/middlewares/persist) - Persist middleware API

### Secondary (MEDIUM confidence)
- [react-grid-layout React 19 issue #2045](https://github.com/react-grid-layout/react-grid-layout/issues/2045) - Closed/resolved; React 19 beta key warning was fixed in RC
- [ilert blog: Why React-Grid-Layout](https://www.ilert.com/blog/building-interactive-dashboards-why-react-grid-layout-was-our-best-choice) - Production experience report
- [npm trends: dnd-kit vs react-grid-layout](https://npmtrends.com/@dnd-kit/core-vs-react-dnd-vs-react-grid-layout) - Download statistics comparison

### Tertiary (LOW confidence)
- [Puck blog: Top 5 DnD Libraries 2026](https://puckeditor.com/blog/top-5-drag-and-drop-libraries-for-react) - General ecosystem overview

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - react-grid-layout v2 is well-documented, recently released TypeScript rewrite; react-hotkeys-hook is widely used
- Architecture: HIGH - Widget registry + zustand persist is a well-established pattern; existing codebase already uses zustand and has similar patterns (selectionStore)
- Pitfalls: HIGH - RGL CSS imports and width prop requirement are well-documented in CHANGELOG; keyboard shortcut pitfalls from react-hotkeys-hook docs

**Research date:** 2026-02-19
**Valid until:** 2026-03-19 (30 days -- stable libraries with recent major release)
