import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { toast } from '@/components/shared/Toast'
import { useTranslationMutations } from '@/hooks/useTranslationMutations'
import { useTranslationQueue } from '@/hooks/useTranslationQueue'
import { ActiveJobCard } from './ActiveJobCard'
import { RecentJobRow } from './RecentJobRow'

export function QueueDashboard() {
  const { t } = useTranslation('settings')
  const { data, error, isLoading } = useTranslationQueue()
  const { cancelJob } = useTranslationMutations()

  const handleCancel = (jobId: string) => {
    cancelJob.mutate(jobId, {
      onSuccess: () =>
        toast(t('translation.queue.cancel_requested'), 'success'),
      onError: (e: Error) => toast(e.message, 'error'),
    })
  }

  return (
    <SettingsDetailLayout
      title={t('translation.queue.title')}
      subtitle={t('translation.queue.subtitle')}
    >
      {error && (
        <div className="mb-4 rounded-lg border border-error bg-error-bg p-4 text-error">
          {t('translation.queue.load_error')}
        </div>
      )}
      {isLoading && (
        <div className="text-muted">
          {t('common.loading', { defaultValue: 'Loading...' })}
        </div>
      )}
      {data && (
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 font-medium">
              {t('translation.queue.active', { n: data.active.length })}
            </h3>
            {data.active.length === 0 ? (
              <div className="text-muted">
                {t('translation.queue.no_active')}
              </div>
            ) : (
              <div className="space-y-2">
                {data.active.map((j) => (
                  <ActiveJobCard
                    key={j.job_id}
                    job={j}
                    onCancel={() => handleCancel(j.job_id)}
                    cancelling={cancelJob.isPending}
                  />
                ))}
              </div>
            )}
          </div>

          <div>
            <h3 className="mb-2 font-medium">
              {t('translation.queue.recent', { n: data.recent.length })}
            </h3>
            {data.recent.length === 0 ? (
              <div className="text-muted">
                {t('translation.queue.no_recent')}
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border">
                {data.recent.map((j) => (
                  <RecentJobRow key={j.job_id} job={j} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </SettingsDetailLayout>
  )
}
