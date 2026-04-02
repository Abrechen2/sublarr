# Activity Navigation Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the Activity navigation from 5 tabs (attention/wanted/progress/completed/blacklist) to 4 clean tabs (queue/translations/history/blacklist), and promote "Wanted" to a top-level sidebar navigation item.

**Architecture:** "Wanted" becomes a standalone route and nav entry like Library. Activity shrinks to 4 tabs mirroring the *arr-standard: Queue (subtitle search operations), Translations (LLM/batch jobs), History, Blacklist. The NeedsAttentionTab is removed — its content is accessible via Wanted's built-in filters.

**Tech Stack:** React 19, React Router, React Query, lucide-react, i18next

---

## File Map

| Action | File | Change |
|--------|------|--------|
| Modify | `frontend/src/components/layout/IconSidebar.tsx` | Add Wanted nav item; move badge from Activity → Wanted |
| Modify | `frontend/src/components/layout/BottomNav.tsx` | Add Wanted nav item; move badge |
| Modify | `frontend/src/App.tsx` | Make `/wanted` a real route (WantedPage); fix redirect tab names |
| Modify | `frontend/src/pages/ActivityPage.tsx` | Replace 5 tabs with 4 new tabs |
| Create | `frontend/src/components/activity/TranslationsTab.tsx` | New component: batch processing + jobs list |
| Modify | `frontend/src/pages/Queue.tsx` | Remove translation sections (batch + jobs); keep search/scanner/probe |
| Modify | `frontend/src/i18n/locales/en/activity.json` | Add tabs keys, translations section |
| Modify | `frontend/src/i18n/locales/de/activity.json` | Same in German |
| Delete | `frontend/src/components/activity/NeedsAttentionTab.tsx` | No longer used |
| Delete | `frontend/src/components/activity/InProgressTab.tsx` | No longer used (thin wrapper) |

---

## Task 1: Add "Wanted" to sidebar navigation

**Files:**
- Modify: `frontend/src/components/layout/IconSidebar.tsx`
- Modify: `frontend/src/components/layout/BottomNav.tsx`

### IconSidebar.tsx

- [ ] **Step 1: Update IconSidebar.tsx**

Replace the file content with the following (adds `Search` icon, adds Wanted nav item between Library and Activity, moves badge from Activity to Wanted):

```tsx
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, BookOpen, Search, Bell, Settings } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useHealth } from '@/hooks/useApi'
import { useWantedSummary } from '@/hooks/useWantedApi'
import { ThemeToggle } from '@/components/shared/ThemeToggle'

interface NavItem {
  readonly to: string
  readonly labelKey: string
  readonly icon: typeof LayoutDashboard
  readonly testId: string
  readonly showBadge?: boolean
}

const mainNavItems: readonly NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, testId: 'nav-link-dashboard' },
  { to: '/library', labelKey: 'nav.library', icon: BookOpen, testId: 'nav-link-library' },
  { to: '/wanted', labelKey: 'nav.wanted', icon: Search, testId: 'nav-link-wanted', showBadge: true },
  { to: '/activity', labelKey: 'nav.activity', icon: Bell, testId: 'nav-link-activity' },
] as const

const bottomNavItems: readonly NavItem[] = [
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, testId: 'nav-link-settings' },
] as const

export function IconSidebar() {
  const { t } = useTranslation('common')
  const { data: health } = useHealth()
  const { data: wantedSummary } = useWantedSummary()

  const wantedCount = wantedSummary?.total ?? 0

  return (
    <aside
      data-testid="icon-sidebar"
      className={cn(
        'icon-sidebar',
        'fixed left-0 top-0 h-screen z-40 flex flex-col',
        'w-[48px] hover:w-[220px] transition-[width] duration-200 ease-in-out',
        'overflow-hidden',
        'hidden md:flex'
      )}
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderRight: '1px solid var(--border)',
      }}
    >
      {/* Logo */}
      <div className="sidebar-logo-area flex items-center py-3 shrink-0" style={{ paddingLeft: 0, paddingRight: 0, justifyContent: 'center' }}>
        <img
          data-testid="sidebar-logo"
          src="/logo-192.png"
          alt="Sublarr"
          className="shrink-0 rounded-[8px]"
          style={{ width: 28, height: 28 }}
        />
        <div className="sidebar-label flex flex-col min-w-0 opacity-0 transition-opacity duration-200">
          <span
            className="text-base font-bold tracking-tight truncate"
            style={{ color: 'var(--accent)' }}
          >
            Sublarr
          </span>
          <span
            data-testid="sidebar-version"
            className="text-[10px] truncate"
            style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
          >
            v{health?.version ?? '...'}
          </span>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 flex flex-col px-1 py-2">
        {mainNavItems.map((item) => (
          <SidebarNavItem
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            badgeCount={item.showBadge ? wantedCount : 0}
          />
        ))}
      </nav>

      {/* Separator */}
      <div
        data-testid="sidebar-separator"
        className="mx-2"
        style={{ borderTop: '1px solid var(--border)' }}
      />

      {/* Bottom Items */}
      <div className="mt-auto px-1 py-2 shrink-0">
        {bottomNavItems.map((item) => (
          <SidebarNavItem
            key={item.to}
            item={item}
            label={t(item.labelKey)}
            badgeCount={0}
          />
        ))}
        <div className="flex items-center justify-center py-1">
          <ThemeToggle />
        </div>
      </div>
    </aside>
  )
}

interface SidebarNavItemProps {
  readonly item: NavItem
  readonly label: string
  readonly badgeCount: number
}

function SidebarNavItem({ item, label, badgeCount }: SidebarNavItemProps) {
  const { to, icon: Icon, testId } = item

  return (
    <NavLink
      to={to}
      end={to === '/'}
      data-testid={testId}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          'sidebar-nav-item flex items-center py-2 mb-0.5 rounded-md relative',
          'transition-colors duration-100',
          !isActive && 'hover:bg-[rgba(255,255,255,0.04)]'
        )
      }
      style={({ isActive }) => ({
        color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
      })}
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <div
              className="absolute left-0 top-[6px] bottom-[6px] w-[3px] rounded-r-sm"
              style={{ backgroundColor: 'var(--accent)' }}
            />
          )}
          <Icon size={20} strokeWidth={isActive ? 2.2 : 1.8} className="shrink-0" />
          <span className="sidebar-label text-[13px] font-medium truncate opacity-0 transition-opacity duration-200">
            {label}
          </span>
          {badgeCount > 0 && (
            <span
              data-testid="wanted-badge"
              className="sidebar-label ml-auto text-[10px] font-bold rounded-full opacity-0 transition-opacity duration-200"
              style={{
                backgroundColor: 'var(--warning)',
                color: '#000',
                padding: '1px 6px',
              }}
            >
              {badgeCount > 99 ? '99+' : badgeCount}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}
```

- [ ] **Step 2: Update BottomNav.tsx**

Replace the nav items array and update the badge logic — move badge from Activity to Wanted:

```tsx
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, BookOpen, Search, Bell, Settings } from 'lucide-react'
import { useWantedSummary } from '@/hooks/useWantedApi'

interface BottomNavItem {
  readonly to: string
  readonly labelKey: string
  readonly icon: typeof LayoutDashboard
  readonly testId: string
  readonly showBadge?: boolean
}

const navItems: readonly BottomNavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, testId: 'bottom-nav-dashboard' },
  { to: '/library', labelKey: 'nav.library', icon: BookOpen, testId: 'bottom-nav-library' },
  { to: '/wanted', labelKey: 'nav.wanted', icon: Search, testId: 'bottom-nav-wanted', showBadge: true },
  { to: '/activity', labelKey: 'nav.activity', icon: Bell, testId: 'bottom-nav-activity' },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings, testId: 'bottom-nav-settings' },
] as const

export function BottomNav() {
  const { t } = useTranslation('common')
  const { data: wantedSummary } = useWantedSummary()

  const wantedCount = wantedSummary?.total ?? 0

  return (
    <nav
      data-testid="bottom-nav"
      className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden"
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderTop: '1px solid var(--border)',
      }}
    >
      {navItems.map(({ to, labelKey, icon: Icon, testId, showBadge }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          data-testid={testId}
          aria-label={t(labelKey)}
          className="flex-1 flex flex-col items-center gap-0.5 py-2 relative transition-colors duration-100"
          style={({ isActive }) => ({
            color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
          })}
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <div
                  className="absolute top-0 left-4 right-4 h-[2px] rounded-b-sm"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
              )}
              <div className="relative">
                <Icon size={22} strokeWidth={isActive ? 2.2 : 1.8} />
                {showBadge && wantedCount > 0 && (
                  <span
                    data-testid="bottom-nav-wanted-badge"
                    className="absolute -top-1 -right-2 text-[9px] font-semibold px-1 min-w-[14px] text-center rounded-full"
                    style={{
                      backgroundColor: 'var(--warning-bg)',
                      color: 'var(--warning)',
                    }}
                  >
                    {wantedCount > 99 ? '99+' : wantedCount}
                  </span>
                )}
              </div>
              <span className="text-[10px] font-medium">{t(labelKey)}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
```

- [ ] **Step 3: Verify the frontend builds without errors**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors related to IconSidebar or BottomNav.

- [ ] **Step 4: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/components/layout/IconSidebar.tsx frontend/src/components/layout/BottomNav.tsx
git commit -m "feat: add Wanted as top-level nav item with badge"
```

---

## Task 2: Make /wanted a standalone route in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add lazy import for WantedPage**

After line 33 (the existing lazy imports block), add:

```tsx
const WantedPage = lazy(() => import('@/pages/Wanted').then(m => ({ default: m.WantedPage })))
```

- [ ] **Step 2: Replace the /wanted redirect with a real route**

Find this line (around line 67):
```tsx
<Route path="/wanted" element={<Navigate to="/activity?tab=wanted" replace />} />
```

Replace with:
```tsx
<Route path="/wanted" element={<Suspense fallback={<PageSkeleton />}><WantedPage /></Suspense>} />
```

- [ ] **Step 3: Fix stale redirect tab names**

Find and replace these two lines:
```tsx
<Route path="/queue" element={<Navigate to="/activity?tab=progress" replace />} />
<Route path="/history" element={<Navigate to="/activity?tab=completed" replace />} />
```

Replace with:
```tsx
<Route path="/queue" element={<Navigate to="/activity?tab=queue" replace />} />
<Route path="/history" element={<Navigate to="/activity?tab=history" replace />} />
```

- [ ] **Step 4: Verify WantedPage has a PageHeader**

Read `frontend/src/pages/Wanted.tsx` and check if it starts with a `PageHeader` component. If it does not have one, add it:

```tsx
import { PageHeader } from '@/components/layout/PageHeader'

// At the top of the return:
<PageHeader
  title={t('page_title', 'Wanted')}
  subtitle={t('page_subtitle', 'Subtitles missing from your library')}
/>
```

The i18n key should already exist in `frontend/src/i18n/locales/en/wanted.json` (or similar). Check the Wanted page's existing `useTranslation` namespace to use the correct one.

- [ ] **Step 5: TypeScript check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No new errors.

- [ ] **Step 6: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/App.tsx frontend/src/pages/Wanted.tsx
git commit -m "feat: make /wanted a standalone route, fix activity redirect tab names"
```

---

## Task 3: Create TranslationsTab component

**Files:**
- Create: `frontend/src/components/activity/TranslationsTab.tsx`

This component extracts the "Batch Processing" panel and "Active/Queued Jobs" list from Queue.tsx and displays them as the Translations tab content.

- [ ] **Step 1: Create TranslationsTab.tsx**

```tsx
import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useJobs, useBatchStatus } from '@/hooks/useApi'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Layers, Loader2 } from 'lucide-react'

const TranslationJobRow = memo(function TranslationJobRow({
  file_path,
  status,
}: {
  file_path: string
  status: 'running' | 'queued'
}) {
  return (
    <div className="px-4 py-2.5 flex items-center gap-3">
      {status === 'running' ? (
        <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)' }} />
      ) : (
        <div className="w-3.5 h-3.5 rounded-full shrink-0" style={{ border: '2px solid var(--warning)' }} />
      )}
      <span
        className="flex-1 truncate"
        title={file_path}
        style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}
      >
        {truncatePath(file_path)}
      </span>
      <StatusBadge status={status} />
    </div>
  )
})

export function TranslationsTab() {
  const { t } = useTranslation('activity')
  const { data: activeJobs } = useJobs(1, 20, 'running', 3000)
  const { data: queuedJobs } = useJobs(1, 20, 'queued', 3000)
  const { data: batch } = useBatchStatus()

  const hasActivity =
    batch?.running ||
    (activeJobs?.data?.length ?? 0) > 0 ||
    (queuedJobs?.data?.length ?? 0) > 0

  return (
    <div className="space-y-5">
      {/* Batch Processing Status */}
      {batch?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--accent)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
            <h2 className="text-sm font-semibold">{t('queue.batch_processing')}</h2>
          </div>
          <ProgressBar value={batch.processed} max={batch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.processed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.processed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.succeeded')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{batch.succeeded}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{batch.failed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.skipped')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{batch.skipped}</span>
            </div>
          </div>
          {batch.current_file && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(batch.current_file, 80)}
            </div>
          )}
        </div>
      )}

      {/* Active Translation Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('queue.running_count', { count: activeJobs?.data?.length ?? 0 })}
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {activeJobs?.data?.length ? (
            activeJobs.data.map((job) => (
              <TranslationJobRow key={job.id} file_path={job.file_path} status="running" />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('translations.no_active', 'No active translation jobs')}
            </div>
          )}
        </div>
      </div>

      {/* Queued Translation Jobs */}
      <div
        className="rounded-lg overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
            {t('queue.queued_count', { count: queuedJobs?.data?.length ?? 0 })}
          </h2>
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
          {queuedJobs?.data?.length ? (
            queuedJobs.data.map((job) => (
              <TranslationJobRow key={job.id} file_path={job.file_path} status="queued" />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('translations.no_queued', 'No queued translation jobs')}
            </div>
          )}
        </div>
      </div>

      {/* Empty state when nothing is happening */}
      {!hasActivity && (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <Layers size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('translations.empty', 'No translation jobs running. Translations start automatically after subtitle download.')}
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors in TranslationsTab.tsx.

- [ ] **Step 3: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/components/activity/TranslationsTab.tsx
git commit -m "feat: create TranslationsTab component for LLM batch jobs"
```

---

## Task 4: Trim Queue.tsx — remove translation sections

**Files:**
- Modify: `frontend/src/pages/Queue.tsx`

Queue.tsx keeps only the subtitle search operations (WantedBatchSearch, BatchProbe, Scanner) and removes translation-related sections (Batch Processing panel + Active/Queued jobs list).

- [ ] **Step 1: Replace Queue.tsx**

```tsx
import { memo } from 'react'
import { useTranslation } from 'react-i18next'
import { useWantedBatchStatus, useWantedBatchProbeStatus, useScannerStatus } from '@/hooks/useApi'
import { ProgressBar } from '@/components/shared/ProgressBar'
import { truncatePath } from '@/lib/utils'
import { Layers, ListVideo, Loader2, ScanSearch, Search } from 'lucide-react'

export function QueuePage() {
  const { t } = useTranslation('activity')
  const { data: wantedBatch } = useWantedBatchStatus()
  const { data: probe } = useWantedBatchProbeStatus()
  const { data: scanner } = useScannerStatus()

  const isActive = wantedBatch?.running || probe?.running || scanner?.is_scanning || scanner?.is_searching

  return (
    <div className="space-y-5">
      {/* Wanted Batch Search Status */}
      {wantedBatch?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--warning)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Search size={16} className="animate-pulse" style={{ color: 'var(--warning)' }} />
            <h2 className="text-sm font-semibold">{t('queue.wanted_batch_searching')}</h2>
          </div>
          <ProgressBar value={wantedBatch.processed} max={wantedBatch.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.processed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.processed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.succeeded')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{wantedBatch.found}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{wantedBatch.failed}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.skipped')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{wantedBatch.skipped}</span>
            </div>
          </div>
          {wantedBatch.current_item && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(wantedBatch.current_item, 80)}
            </div>
          )}
        </div>
      )}

      {/* Batch Probe Status */}
      {probe?.running && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--accent)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Layers size={16} className="animate-pulse" style={{ color: 'var(--accent)' }} />
            <h2 className="text-sm font-semibold">{t('queue.batch_probe_running')}</h2>
          </div>
          <ProgressBar value={probe.extracted ?? 0} max={probe.total} className="mb-3" />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.total')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{probe.total}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.found')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{probe.found}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.extracted')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{probe.extracted}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.failed')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}>{probe.failed}</span>
            </div>
          </div>
          {probe.current_item && (
            <div
              className="mt-3 text-xs truncate"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
            >
              {t('queue.current')}: {truncatePath(probe.current_item, 80)}
            </div>
          )}
        </div>
      )}

      {/* Wanted Scanner Status */}
      {(scanner?.is_scanning || scanner?.is_searching) && (
        <div
          className="rounded-lg p-4"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderLeft: '3px solid var(--success)',
          }}
        >
          <div className="flex items-center gap-2 mb-3">
            <ScanSearch size={16} className="animate-pulse" style={{ color: 'var(--success)' }} />
            <h2 className="text-sm font-semibold">{t('queue.scanner_running')}</h2>
            {scanner.progress.phase && (
              <span
                className="text-xs px-2 py-0.5 rounded"
                style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-muted)' }}
              >
                {scanner.progress.phase}
              </span>
            )}
          </div>
          {scanner.progress.total > 0 && (
            <ProgressBar value={scanner.progress.current} max={scanner.progress.total} className="mb-3" />
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.progress')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {scanner.progress.current}/{scanner.progress.total}
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.added')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{scanner.progress.added}</span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('queue.updated')}: </span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{scanner.progress.updated}</span>
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isActive && (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <ListVideo size={32} className="mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {t('queue.empty', 'No active subtitle searches. Use "Search All" on the Wanted page to start.')}
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/Queue.tsx
git commit -m "refactor: remove translation sections from Queue, keep subtitle search only"
```

---

## Task 5: Rewrite ActivityPage.tsx with 4 new tabs

**Files:**
- Modify: `frontend/src/pages/ActivityPage.tsx`

- [ ] **Step 1: Replace ActivityPage.tsx**

```tsx
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { PillTabs } from '@/components/shared/PillTabs'
import { TranslationsTab } from '@/components/activity/TranslationsTab'
import { QueuePage } from '@/pages/Queue'
import { HistoryPage } from '@/pages/History'
import { BlacklistPage } from '@/pages/Blacklist'
import { useJobs } from '@/hooks/useApi'

// ─── Types ────────────────────────────────────────────────────────────────────

const VALID_TABS = ['queue', 'translations', 'history', 'blacklist'] as const
type TabId = typeof VALID_TABS[number]

const DEFAULT_TAB: TabId = 'queue'

function isValidTab(value: string | null): value is TabId {
  return value !== null && (VALID_TABS as readonly string[]).includes(value)
}

// ─── ActivityPage ─────────────────────────────────────────────────────────────

export function ActivityPage() {
  const { t } = useTranslation('activity')
  const [searchParams, setSearchParams] = useSearchParams()

  const rawTab = searchParams.get('tab')
  const activeTab: TabId = isValidTab(rawTab) ? rawTab : DEFAULT_TAB

  const handleTabChange = useCallback(
    (tabId: string) => {
      if (isValidTab(tabId)) {
        setSearchParams({ tab: tabId }, { replace: true })
      }
    },
    [setSearchParams],
  )

  // Badge: active + queued translation jobs for the Translations tab
  const { data: activeJobs } = useJobs(1, 20, 'running', 3000)
  const { data: queuedJobs } = useJobs(1, 20, 'queued', 3000)

  const translationsCount =
    (activeJobs?.data?.length ?? 0) + (queuedJobs?.data?.length ?? 0) || undefined

  const tabs = useMemo(
    () => [
      { id: 'queue' as const, label: t('tabs.queue', 'Queue') },
      { id: 'translations' as const, label: t('tabs.translations', 'Translations'), count: translationsCount },
      { id: 'history' as const, label: t('tabs.history', 'History') },
      { id: 'blacklist' as const, label: t('tabs.blacklist', 'Blacklist') },
    ],
    [t, translationsCount],
  )

  return (
    <div data-testid="activity-page" className="space-y-5">
      <PageHeader
        title={t('page_title', 'Activity')}
        subtitle={t('page_subtitle', 'Monitor subtitle searches, downloads, and translation jobs')}
      />

      <PillTabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} />

      <div data-testid={`tab-content-${activeTab}`}>
        {activeTab === 'queue' && <QueuePage />}
        {activeTab === 'translations' && <TranslationsTab />}
        {activeTab === 'history' && <HistoryPage />}
        {activeTab === 'blacklist' && <BlacklistPage />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/pages/ActivityPage.tsx
git commit -m "feat: refactor ActivityPage to 4 tabs (queue/translations/history/blacklist)"
```

---

## Task 6: Update i18n files

**Files:**
- Modify: `frontend/src/i18n/locales/en/activity.json`
- Modify: `frontend/src/i18n/locales/de/activity.json`

- [ ] **Step 1: Update English activity.json**

Add the `tabs`, `page_title`, `page_subtitle`, and `translations` keys. The existing `queue`, `history`, `blacklist` sections stay unchanged. Add to the root of the JSON (alongside existing keys):

```json
{
  "page_title": "Activity",
  "page_subtitle": "Monitor subtitle searches, downloads, and translation jobs",
  "tabs": {
    "queue": "Queue",
    "translations": "Translations",
    "history": "History",
    "blacklist": "Blacklist"
  },
  "translations": {
    "no_active": "No active translation jobs",
    "no_queued": "No queued translation jobs",
    "empty": "No translation jobs running. Translations start automatically after subtitle download."
  },
  "queue": {
    "empty": "No active subtitle searches. Use \"Search All\" on the Wanted page to start.",
    ...existing queue keys...
  },
  ...existing keys...
}
```

The full merged en/activity.json:

```json
{
  "page_title": "Activity",
  "page_subtitle": "Monitor subtitle searches, downloads, and translation jobs",
  "tabs": {
    "queue": "Queue",
    "translations": "Translations",
    "history": "History",
    "blacklist": "Blacklist"
  },
  "title": "Translations",
  "filter": {
    "all": "All",
    "completed": "Completed",
    "failed": "Failed",
    "running": "Running",
    "queued": "Queued"
  },
  "table": {
    "content": "Content",
    "status": "Status",
    "lang": "Language",
    "format": "Format",
    "time": "Time",
    "error": "Error",
    "actions": "Actions"
  },
  "expanded": {
    "full_path": "Input File",
    "output": "Output File",
    "format": "Format",
    "force": "Forced",
    "force_yes": "Yes",
    "force_no": "No",
    "created": "Created",
    "completed": "Completed",
    "error": "Error",
    "stats": "Stats",
    "source": "Source",
    "lines": "lines"
  },
  "no_jobs": "No jobs found",
  "retry_started": "Retry started",
  "retry_failed": "Retry failed",
  "retry_job": "Retry job",
  "page_info": "Page {{page}} of {{totalPages}} ({{total}} total)",
  "translations": {
    "no_active": "No active translation jobs",
    "no_queued": "No queued translation jobs",
    "empty": "No translation jobs running. Translations start automatically after subtitle download."
  },
  "queue": {
    "title": "Queue",
    "batch_processing": "Batch Processing",
    "wanted_batch_searching": "Wanted Batch Search Running",
    "batch_probe_running": "Batch Probe Running",
    "total": "Total",
    "processed": "Processed",
    "succeeded": "Succeeded",
    "failed": "Failed",
    "skipped": "Skipped",
    "found": "Found",
    "extracted": "Extracted",
    "scanner_running": "Wanted Scanner Running",
    "progress": "Progress",
    "added": "Added",
    "updated": "Updated",
    "current": "Current",
    "running": "Running",
    "running_count": "Running ({{count}})",
    "queued": "Queued",
    "queued_count": "Queued ({{count}})",
    "no_active": "No active translations",
    "no_queued": "No queued jobs",
    "empty": "No active subtitle searches. Use \"Search All\" on the Wanted page to start."
  },
  "history": {
    "title": "Downloads",
    "subtitle": "Subtitle download history across all providers",
    "total_downloads": "Total Downloads",
    "last_24h": "Last 24h",
    "last_7d": "Last 7 Days",
    "top_provider": "Top Provider",
    "all_providers": "All Providers",
    "table": {
      "content": "Content",
      "provider": "Provider",
      "lang": "Lang",
      "format": "Format",
      "score": "Score",
      "date": "Date",
      "actions": "Actions"
    },
    "no_history": "No download history yet",
    "add_to_blacklist": "Add to blacklist",
    "blacklisted_from_history": "Blacklisted from history",
    "blacklist_confirm_title": "Add to Blacklist",
    "blacklist_confirm_from": "Block subtitle from",
    "blacklist_confirm_action": "Blacklist",
    "blacklist_also_delete": "Also delete the file",
    "blacklisted_success": "Added to blacklist",
    "deleted_and_blacklisted": "Subtitle deleted and blacklisted"
  },
  "blacklist": {
    "title": "Blacklist",
    "subtitle": "{{count}} blacklisted subtitles will be excluded from search results",
    "blocked_subtitles": "Blocked Subtitles",
    "clear_all": "Clear All",
    "clear_confirm": "Clear all entries?",
    "table": {
      "provider": "Provider",
      "subtitle_id": "Subtitle ID",
      "lang": "Lang",
      "title_path": "Title / Path",
      "reason": "Reason",
      "added": "Added",
      "actions": "Actions"
    },
    "no_items": "No blacklisted subtitles. Use the ban button on search results or history to block unwanted subtitles.",
    "remove_from_blacklist": "Remove from blacklist"
  }
}
```

- [ ] **Step 2: Update German activity.json**

Same structure in German:

```json
{
  "page_title": "Aktivität",
  "page_subtitle": "Untertitel-Suche, Downloads und Übersetzungsjobs überwachen",
  "tabs": {
    "queue": "Warteschlange",
    "translations": "Übersetzungen",
    "history": "Verlauf",
    "blacklist": "Sperrliste"
  },
  "title": "Übersetzungen",
  "filter": {
    "all": "Alle",
    "completed": "Abgeschlossen",
    "failed": "Fehlgeschlagen",
    "running": "Läuft",
    "queued": "Wartend"
  },
  "table": {
    "content": "Inhalt",
    "status": "Status",
    "lang": "Sprache",
    "format": "Format",
    "time": "Zeit",
    "error": "Fehler",
    "actions": "Aktionen"
  },
  "expanded": {
    "full_path": "Eingabedatei",
    "output": "Ausgabedatei",
    "format": "Format",
    "force": "Erzwungen",
    "force_yes": "Ja",
    "force_no": "Nein",
    "created": "Erstellt",
    "completed": "Abgeschlossen",
    "error": "Fehler",
    "stats": "Statistiken",
    "source": "Quelle",
    "lines": "Zeilen"
  },
  "no_jobs": "Keine Aufgaben gefunden",
  "retry_started": "Wiederholung gestartet",
  "retry_failed": "Wiederholung fehlgeschlagen",
  "retry_job": "Aufgabe wiederholen",
  "page_info": "Seite {{page}} von {{totalPages}} ({{total}} gesamt)",
  "translations": {
    "no_active": "Keine aktiven Übersetzungsjobs",
    "no_queued": "Keine wartenden Übersetzungsjobs",
    "empty": "Keine Übersetzungsjobs aktiv. Übersetzungen starten automatisch nach dem Untertitel-Download."
  },
  "queue": {
    "title": "Warteschlange",
    "batch_processing": "Stapelverarbeitung",
    "wanted_batch_searching": "Wanted-Suche läuft",
    "batch_probe_running": "Batch-Probe läuft",
    "total": "Gesamt",
    "processed": "Verarbeitet",
    "succeeded": "Erfolgreich",
    "failed": "Fehlgeschlagen",
    "skipped": "Übersprungen",
    "found": "Gefunden",
    "extracted": "Extrahiert",
    "scanner_running": "Wanted-Scanner läuft",
    "progress": "Fortschritt",
    "added": "Neu",
    "updated": "Aktualisiert",
    "current": "Aktuell",
    "running": "Aktiv",
    "running_count": "Aktiv ({{count}})",
    "queued": "Wartend",
    "queued_count": "Wartend ({{count}})",
    "no_active": "Keine aktiven Übersetzungen",
    "no_queued": "Keine wartenden Aufgaben",
    "empty": "Keine aktiven Untertitel-Suchen. Nutze \"Alle suchen\" auf der Wanted-Seite."
  },
  "history": {
    "title": "Downloads",
    "subtitle": "Untertitel-Download-Verlauf aller Provider",
    "total_downloads": "Downloads gesamt",
    "last_24h": "Letzte 24 Std.",
    "last_7d": "Letzte 7 Tage",
    "top_provider": "Top Provider",
    "all_providers": "Alle Provider",
    "table": {
      "content": "Inhalt",
      "provider": "Provider",
      "lang": "Sprache",
      "format": "Format",
      "score": "Score",
      "date": "Datum",
      "actions": "Aktionen"
    },
    "no_history": "Noch kein Download-Verlauf",
    "add_to_blacklist": "Zur Sperrliste hinzufügen",
    "blacklisted_from_history": "Aus dem Verlauf gesperrt",
    "blacklist_confirm_title": "Zur Sperrliste hinzufügen",
    "blacklist_confirm_from": "Untertitel sperren von",
    "blacklist_confirm_action": "Sperren",
    "blacklist_also_delete": "Datei ebenfalls löschen",
    "blacklisted_success": "Zur Sperrliste hinzugefügt",
    "deleted_and_blacklisted": "Untertitel gelöscht und gesperrt"
  },
  "blacklist": {
    "title": "Sperrliste",
    "subtitle": "{{count}} gesperrte Untertitel werden aus den Suchergebnissen ausgeschlossen",
    "blocked_subtitles": "Gesperrte Untertitel",
    "clear_all": "Alle leeren",
    "clear_confirm": "Alle Einträge leeren?",
    "table": {
      "provider": "Provider",
      "subtitle_id": "Untertitel-ID",
      "lang": "Sprache",
      "title_path": "Titel / Pfad",
      "reason": "Grund",
      "added": "Hinzugefügt",
      "actions": "Aktionen"
    },
    "no_items": "Keine gesperrten Untertitel. Verwende den Sperren-Button bei Suchergebnissen oder im Verlauf, um unerwünschte Untertitel zu blockieren.",
    "remove_from_blacklist": "Von Sperrliste entfernen"
  }
}
```

- [ ] **Step 3: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add frontend/src/i18n/locales/en/activity.json frontend/src/i18n/locales/de/activity.json
git commit -m "feat: update activity i18n for new 4-tab structure"
```

---

## Task 7: Delete obsolete components

**Files:**
- Delete: `frontend/src/components/activity/NeedsAttentionTab.tsx`
- Delete: `frontend/src/components/activity/InProgressTab.tsx`

- [ ] **Step 1: Verify neither file is still imported anywhere**

```bash
cd D:/Sublarr_Projekt/Sublarr
grep -r "NeedsAttentionTab\|InProgressTab" frontend/src --include="*.tsx" --include="*.ts"
```

Expected: No results (both files should no longer be imported after Task 5).

- [ ] **Step 2: Delete the files**

```bash
rm frontend/src/components/activity/NeedsAttentionTab.tsx
rm frontend/src/components/activity/InProgressTab.tsx
```

- [ ] **Step 3: Final TypeScript check**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npx tsc --noEmit 2>&1 | head -40
```

Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add -A frontend/src/components/activity/
git commit -m "chore: delete obsolete NeedsAttentionTab and InProgressTab components"
```

---

## Task 8: Local testing and verification

- [ ] **Step 1: Run frontend dev server**

```bash
cd D:/Sublarr_Projekt/Sublarr && npm run dev:frontend
```

Open http://localhost:5173 in a browser.

- [ ] **Step 2: Verify navigation**

Check:
- Sidebar shows: Dashboard, Library, **Wanted**, Activity, Settings
- Wanted badge shows count of wanted items
- Clicking Wanted opens `/wanted` standalone page (not a redirect to Activity)
- Clicking Activity opens `/activity` with tab "Queue" active by default

- [ ] **Step 3: Verify Activity tabs**

Check:
- Queue tab: shows "Wanted Batch Search", "Batch Probe", "Scanner" panels (only when active), empty state otherwise
- Translations tab: shows "Batch Processing" + jobs list, empty state when idle
- History tab: shows download history as before
- Blacklist tab: shows blacklist as before

- [ ] **Step 4: Run frontend unit tests**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run test -- --run 2>&1 | tail -20
```

Expected: All tests pass (or same failures as before the change — no regressions introduced).

- [ ] **Step 5: Run linter**

```bash
cd D:/Sublarr_Projekt/Sublarr/frontend && npm run lint 2>&1 | tail -20
```

Expected: No new errors.

- [ ] **Step 6: Final commit if any lint fixes needed**

```bash
cd D:/Sublarr_Projekt/Sublarr
git add -A frontend/src/
git commit -m "fix: lint cleanup after activity nav restructure"
```
