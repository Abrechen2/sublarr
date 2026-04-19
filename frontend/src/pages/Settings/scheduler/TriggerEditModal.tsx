import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type {
  SchedulerJob,
  Trigger,
  TriggerCron,
  TriggerInterval,
} from '@/lib/types'
import { IntervalEditor } from './IntervalEditor'
import { CronEditor } from './CronEditor'

type Tab = 'interval' | 'cron'

export function TriggerEditModal({
  job,
  open,
  onClose,
  onSubmit,
  isSubmitting = false,
  error = null,
}: {
  job: SchedulerJob
  open: boolean
  onClose: () => void
  onSubmit: (trigger: Trigger) => void
  isSubmitting?: boolean
  error?: string | null
}) {
  const { t } = useTranslation('settings')
  const initialTab: Tab = job.trigger.type
  const [tab, setTab] = useState<Tab>(initialTab)
  const [interval, setInterval] = useState<TriggerInterval>(
    job.trigger.type === 'interval'
      ? job.trigger
      : { type: 'interval', minutes: 15 },
  )
  const [cron, setCron] = useState<TriggerCron>(
    job.trigger.type === 'cron'
      ? job.trigger
      : { type: 'cron', hour: '3', minute: '0' },
  )

  if (!open) return null

  const payload: Trigger = tab === 'interval' ? interval : cron

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-xl rounded-lg bg-surface p-5 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">
            {t('scheduler.edit_trigger_for', { job: job.id })}
          </h2>
          <button
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
          >
            <X size={20} />
          </button>
        </div>

        <div className="mb-4 flex gap-2 border-b border-border">
          {(['interval', 'cron'] as Tab[]).map((tname) => (
            <button
              key={tname}
              type="button"
              onClick={() => setTab(tname)}
              className={`px-3 py-2 text-sm ${
                tab === tname
                  ? 'border-b-2 border-accent font-medium text-accent'
                  : 'text-muted'
              }`}
            >
              {t(`scheduler.tab_${tname}`)}
            </button>
          ))}
        </div>

        {tab === 'interval' ? (
          <IntervalEditor value={interval} onChange={setInterval} />
        ) : (
          <CronEditor value={cron} onChange={setCron} />
        )}

        {error && (
          <div className="mt-3 rounded-md bg-error-bg p-2 text-sm text-error">
            {error}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1 text-sm"
          >
            {t('common.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button
            onClick={() => onSubmit(payload)}
            disabled={isSubmitting}
            className="rounded-md bg-accent px-3 py-1 text-sm text-white disabled:opacity-50"
          >
            {isSubmitting
              ? t('common.saving', { defaultValue: 'Saving…' })
              : t('common.save', { defaultValue: 'Save' })}
          </button>
        </div>
      </div>
    </div>
  )
}
