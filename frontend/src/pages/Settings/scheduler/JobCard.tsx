import { useState } from 'react'
import type { SchedulerJob, Trigger } from '@/lib/types'
import { useTranslation } from 'react-i18next'
import { StatusBadge } from './StatusBadge'
import { TriggerEditModal } from './TriggerEditModal'
import { useSchedulerMutations } from '@/hooks/useSchedulerMutations'
import { toast } from '@/components/shared/Toast'
import { Play, Pause, Edit3, History, RotateCcw } from 'lucide-react'

function triggerLabel(
  job: SchedulerJob,
  t: (k: string, o?: Record<string, unknown>) => string,
): string {
  const trig = job.trigger
  if (trig.type === 'interval') {
    const s = trig.seconds ?? 0
    if (s >= 3600) return t('scheduler.every_hours', { n: Math.round(s / 3600) })
    if (s >= 60) return t('scheduler.every_minutes', { n: Math.round(s / 60) })
    return t('scheduler.every_seconds', { n: s })
  }
  const hour = trig.hour ?? '*'
  const minute = trig.minute ?? '*'
  const dow = trig.day_of_week
  if (dow) return t('scheduler.cron_weekly', { dow, hour, minute })
  return t('scheduler.cron_daily', { hour, minute })
}

function relativeTime(
  iso: string | null,
  t: (k: string, o?: Record<string, unknown>) => string,
): string {
  if (!iso) return t('scheduler.never', { defaultValue: '—' })
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (Math.abs(diff) < 60) return t('scheduler.just_now')
  if (Math.abs(diff) < 3600)
    return t('scheduler.minutes_ago', { n: Math.round(Math.abs(diff) / 60) })
  return t('scheduler.hours_ago', { n: Math.round(Math.abs(diff) / 3600) })
}

export function JobCard({
  job,
  onOpenHistory,
}: {
  job: SchedulerJob
  onOpenHistory: () => void
}) {
  const { t } = useTranslation('settings')
  const [editOpen, setEditOpen] = useState(false)
  const mut = useSchedulerMutations(job.id)

  const errMsg = (e: unknown, fallback: string): string =>
    e instanceof Error ? e.message : fallback

  const handleRunNow = () => {
    mut.runNow.mutate(undefined, {
      onSuccess: () => toast(t('scheduler.toast.queued')),
      onError: (e: unknown) => toast(errMsg(e, 'Failed'), 'error'),
    })
  }

  const handlePauseResume = () => {
    if (job.paused) {
      mut.resume.mutate(undefined, {
        onSuccess: () => toast(t('scheduler.toast.resumed')),
        onError: (e: unknown) => toast(errMsg(e, 'Failed'), 'error'),
      })
    } else {
      mut.pause.mutate(undefined, {
        onSuccess: () => toast(t('scheduler.toast.paused')),
        onError: (e: unknown) => toast(errMsg(e, 'Failed'), 'error'),
      })
    }
  }

  const handleReset = () => {
    if (!confirm(t('scheduler.confirm_reset'))) return
    mut.resetDefault.mutate(undefined, {
      onSuccess: () => toast(t('scheduler.toast.reset')),
      onError: (e: unknown) => toast(errMsg(e, 'Failed'), 'error'),
    })
  }

  const handleSaveTrigger = (trigger: Trigger) => {
    mut.patchTrigger.mutate(trigger, {
      onSuccess: () => {
        toast(t('scheduler.toast.updated'))
        setEditOpen(false)
      },
      // On error: keep modal open; error message surfaces via mut.patchTrigger.error
    })
  }

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-foreground">{job.id}</h3>
            {!job.trigger_is_default && (
              <span className="rounded-full bg-elevated px-2 py-0.5 text-xs text-muted">
                {t('scheduler.edited')}
              </span>
            )}
            {job.paused && (
              <span className="rounded-full bg-warning-bg px-2 py-0.5 text-xs text-warning">
                {t('scheduler.paused')}
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted">
            {triggerLabel(job, t)} · {job.owner_module}
          </p>
          {job.description && (
            <p className="mt-1 text-sm text-secondary">{job.description}</p>
          )}
        </div>
        {job.last_run?.status && <StatusBadge status={job.last_run.status} />}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-muted">{t('scheduler.last_run')}</div>
          <div>{relativeTime(job.last_run?.finished_at ?? null, t)}</div>
        </div>
        <div>
          <div className="text-muted">{t('scheduler.next_run')}</div>
          <div>{relativeTime(job.next_run_time, t)}</div>
        </div>
      </div>

      <div className="mt-3 text-xs text-muted">
        7d: {job.stats_7d.ok} ok · {job.stats_7d.error} err · {job.stats_7d.timeout} to ·{' '}
        {job.stats_7d.missed} miss
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={handleRunNow}
          disabled={mut.runNow.isPending}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-elevated disabled:opacity-50"
        >
          <Play size={14} /> {t('scheduler.run_now')}
        </button>
        <button
          onClick={handlePauseResume}
          disabled={mut.pause.isPending || mut.resume.isPending}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-elevated disabled:opacity-50"
        >
          {job.paused ? <Play size={14} /> : <Pause size={14} />}
          {job.paused ? t('scheduler.resume') : t('scheduler.pause')}
        </button>
        <button
          onClick={() => setEditOpen(true)}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-elevated"
        >
          <Edit3 size={14} /> {t('scheduler.edit_trigger')}
        </button>
        <button
          onClick={onOpenHistory}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-elevated"
        >
          <History size={14} /> {t('scheduler.history')}
        </button>
        <button
          onClick={handleReset}
          disabled={job.trigger_is_default || mut.resetDefault.isPending}
          className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1 text-sm hover:bg-elevated disabled:opacity-50"
        >
          <RotateCcw size={14} /> {t('scheduler.reset_default')}
        </button>
      </div>

      <TriggerEditModal
        job={job}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSubmit={handleSaveTrigger}
        isSubmitting={mut.patchTrigger.isPending}
        error={
          mut.patchTrigger.error instanceof Error
            ? mut.patchTrigger.error.message
            : null
        }
      />
    </div>
  )
}
