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
