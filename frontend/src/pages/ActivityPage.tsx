import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { PillTabs } from '@/components/shared/PillTabs'
import { NeedsAttentionTab } from '@/components/activity/NeedsAttentionTab'
import { InProgressTab } from '@/components/activity/InProgressTab'
import { WantedPage } from '@/pages/Wanted'
import { HistoryPage } from '@/pages/History'
import { BlacklistPage } from '@/pages/Blacklist'
import { useWantedItems } from '@/hooks/useApi'
import { useJobs } from '@/hooks/useApi'
import type { WantedItem } from '@/lib/types'

// ─── Types ────────────────────────────────────────────────────────────────────

const VALID_TABS = ['attention', 'wanted', 'progress', 'completed', 'blacklist'] as const
type TabId = typeof VALID_TABS[number]

const DEFAULT_TAB: TabId = 'wanted'

function isValidTab(value: string | null): value is TabId {
  return value !== null && (VALID_TABS as readonly string[]).includes(value)
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function countAttentionItems(items: readonly WantedItem[]): number {
  return items.filter(
    (item) => item.status === 'failed' || (item.current_score > 0 && item.current_score < 50),
  ).length
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

  // Fetch counts for tab badges
  const { data: wantedData } = useWantedItems(1, 100)
  const { data: activeJobs } = useJobs(1, 20, 'running', 3000)
  const { data: queuedJobs } = useJobs(1, 20, 'queued', 3000)

  const attentionCount = useMemo(
    () => countAttentionItems(wantedData?.data ?? []),
    [wantedData?.data],
  )

  const wantedCount = wantedData?.total ?? undefined
  const progressCount =
    (activeJobs?.data?.length ?? 0) + (queuedJobs?.data?.length ?? 0) || undefined

  const tabs = useMemo(
    () => [
      { id: 'attention' as const, label: t('tabs.attention', 'Needs Attention'), count: attentionCount || undefined },
      { id: 'wanted' as const, label: t('tabs.wanted', 'Wanted'), count: wantedCount },
      { id: 'progress' as const, label: t('tabs.progress', 'In Progress'), count: progressCount },
      { id: 'completed' as const, label: t('tabs.completed', 'Completed') },
      { id: 'blacklist' as const, label: t('tabs.blacklist', 'Blacklist') },
    ],
    [t, attentionCount, wantedCount, progressCount],
  )

  return (
    <div data-testid="activity-page" className="space-y-5">
      <PageHeader
        title={t('page_title', 'Activity')}
        subtitle={t('page_subtitle', 'Track subtitle searches, downloads, and issues')}
      />

      <PillTabs tabs={tabs} activeTab={activeTab} onChange={handleTabChange} />

      <div data-testid={`tab-content-${activeTab}`}>
        {activeTab === 'attention' && <NeedsAttentionTab />}
        {activeTab === 'wanted' && <WantedPage />}
        {activeTab === 'progress' && <InProgressTab />}
        {activeTab === 'completed' && <HistoryPage />}
        {activeTab === 'blacklist' && <BlacklistPage />}
      </div>
    </div>
  )
}
