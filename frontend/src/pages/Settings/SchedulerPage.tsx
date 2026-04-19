import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { useSchedulerJobs } from '@/hooks/useSchedulerJobs'
import { JobCard } from './scheduler/JobCard'
import { JobHistoryDrawer } from './scheduler/JobHistoryDrawer'

export function SchedulerPage() {
  const { t } = useTranslation('settings')
  const { data, isLoading, error } = useSchedulerJobs()
  const [historyJob, setHistoryJob] = useState<string | null>(null)

  return (
    <SettingsDetailLayout
      title={t('scheduler.title')}
      subtitle={t('scheduler.subtitle')}
    >
      {error && (
        <div
          className="mb-4 rounded-lg border border-error bg-error-bg p-4 text-error"
          data-testid="scheduler-down-error"
        >
          {t('scheduler.down_error')}
        </div>
      )}
      {isLoading && (
        <div className="text-muted" data-testid="scheduler-loading">
          {t('common.loading', { defaultValue: 'Loading...' })}
        </div>
      )}
      {data && (
        <div className="space-y-3" data-testid="scheduler-job-list">
          {data.jobs.map((j) => (
            <JobCard
              key={j.id}
              job={j}
              onOpenHistory={() => setHistoryJob(j.id)}
            />
          ))}
        </div>
      )}
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
