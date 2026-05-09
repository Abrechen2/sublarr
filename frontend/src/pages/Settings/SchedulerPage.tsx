import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'

import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { useSchedulerJobs } from '@/hooks/useSchedulerJobs'
import type { SchedulerJob } from '@/lib/types'

import { JobRow } from './scheduler/JobRow'
import { JobHistoryDrawer } from './scheduler/JobHistoryDrawer'
import {
  JOB_CATEGORIES,
  categorize,
  type JobCategory,
} from './scheduler/jobMeta'

export function SchedulerPage() {
  const { t } = useTranslation('settings')
  const { data, isLoading, error } = useSchedulerJobs()
  const [historyJob, setHistoryJob] = useState<string | null>(null)

  // Group jobs by category once per data update — keeps render shape
  // stable when jobs come and go.
  const grouped = useMemo<Record<JobCategory, SchedulerJob[]>>(() => {
    const out: Record<JobCategory, SchedulerJob[]> = {
      scanning: [],
      metadata: [],
      maintenance: [],
    }
    if (!data) return out
    for (const job of data.jobs) {
      out[categorize(job.id)].push(job)
    }
    // Stable name-sort within each group so the page doesn't reorder
    // when stats refresh.
    for (const cat of Object.keys(out) as JobCategory[]) {
      out[cat].sort((a, b) => a.id.localeCompare(b.id))
    }
    return out
  }, [data])

  return (
    <SettingsDetailLayout
      title={t('scheduler.title')}
      subtitle={t('scheduler.subtitle')}
    >
      {error && (
        <div
          data-testid="scheduler-down-error"
          className="flex items-start gap-2 rounded-md border p-3 text-[13px]"
          style={{
            borderColor: 'var(--error)',
            background: 'var(--error-bg)',
            color: 'var(--error)',
          }}
        >
          <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
          <span>{t('scheduler.down_error')}</span>
        </div>
      )}

      {isLoading && (
        <div
          data-testid="scheduler-loading"
          className="animate-pulse space-y-3"
          aria-busy="true"
        >
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-32 rounded-lg"
              style={{ background: 'var(--bg-surface)' }}
            />
          ))}
        </div>
      )}

      {data &&
        JOB_CATEGORIES.map((cat) => {
          const jobs = grouped[cat.id]
          if (jobs.length === 0) return null
          const Icon = cat.icon
          return (
            <SettingsSection
              key={cat.id}
              title={t(cat.titleKey)}
              description={t(cat.descKey)}
              icon={<Icon size={16} style={{ color: 'var(--accent)' }} />}
            >
              <div data-testid={`scheduler-group-${cat.id}`}>
                {jobs.map((j, idx) => (
                  <JobRow
                    key={j.id}
                    job={j}
                    onOpenHistory={() => setHistoryJob(j.id)}
                    isLast={idx === jobs.length - 1}
                  />
                ))}
              </div>
            </SettingsSection>
          )
        })}

      {historyJob && (
        <JobHistoryDrawer
          jobId={historyJob}
          open
          onClose={() => setHistoryJob(null)}
        />
      )}
    </SettingsDetailLayout>
  )
}
