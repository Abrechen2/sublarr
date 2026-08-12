import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Edit3,
  History,
  Pause,
  Play,
  RotateCcw,
} from 'lucide-react'

import { toast } from '@/components/shared/Toast'
import { useSchedulerMutations } from '@/hooks/useSchedulerMutations'
import type { SchedulerJob, Trigger } from '@/lib/types'

import { HealthBar } from './HealthBar'
import { KebabMenu } from './KebabMenu'
import { TriggerEditModal } from './TriggerEditModal'
import { jobDescKey, jobNameKey } from './jobMeta'

// Status dot colour: derived from the most recent run.
function statusDotColor(status?: string | null): string {
  switch (status) {
    case 'ok':
      return 'var(--success)'
    // 'timeout_abandoned' belongs here rather than with the warnings: the run
    // never ended — the job was asked to stop and did not.
    case 'error':
    case 'timeout_abandoned':
      return 'var(--error)'
    case 'timeout':
    case 'missed':
      return 'var(--warning)'
    case 'skipped_overlap':
      return 'var(--text-muted)'
    default:
      return 'var(--border)'
  }
}

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
  // The sign matters: this same helper renders "Last run" (past) and "Next run"
  // (future). Taking the absolute value and formatting both with the past-tense
  // strings made every scheduled job read "2 h ago" — including one that had
  // just run and was due again in two minutes.
  const future = diff < 0
  const abs = Math.abs(diff)
  if (abs < 60) return t(future ? 'scheduler.due_now' : 'scheduler.just_now')
  if (abs < 3600)
    return t(future ? 'scheduler.in_minutes' : 'scheduler.minutes_ago', {
      n: Math.round(abs / 60),
    })
  return t(future ? 'scheduler.in_hours' : 'scheduler.hours_ago', {
    n: Math.round(abs / 3600),
  })
}

export function JobRow({
  job,
  onOpenHistory,
  isLast,
}: {
  job: SchedulerJob
  onOpenHistory: () => void
  isLast?: boolean
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
    })
  }

  const friendlyName = t(jobNameKey(job.id), { defaultValue: job.id })
  const friendlyDesc = t(jobDescKey(job.id), {
    defaultValue: job.description ?? '',
  })

  const dotColor = statusDotColor(job.last_run?.status)

  return (
    <>
      <div
        data-testid={`scheduler-job-row-${job.id}`}
        className="flex items-start gap-3 py-3"
        style={{
          borderBottom: isLast ? 'none' : '1px solid var(--border)',
        }}
      >
        {/* Status dot — colour-coded by last_run.status */}
        <div
          className="mt-1 flex-shrink-0"
          aria-label={
            job.last_run?.status
              ? t(`scheduler.status.${job.last_run.status}`, {
                  defaultValue: job.last_run.status,
                })
              : 'idle'
          }
        >
          <span
            className="block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: dotColor }}
          />
        </div>

        {/* Centre column: name + meta + schedule + health bar */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[14px] font-medium text-[var(--text-primary)]">
              {friendlyName}
            </span>
            <span
              className="rounded text-[10px] uppercase tracking-wide text-[var(--text-muted)]"
              style={{
                fontFamily: 'var(--font-mono, ui-monospace, monospace)',
                background: 'var(--bg-elevated)',
                padding: '1px 6px',
              }}
            >
              {job.id}
            </span>
            {!job.trigger_is_default && (
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={{
                  background: 'var(--bg-elevated)',
                  color: 'var(--text-muted)',
                }}
              >
                {t('scheduler.edited')}
              </span>
            )}
            {job.paused && (
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={{
                  background: 'var(--warning-bg)',
                  color: 'var(--warning)',
                }}
              >
                {t('scheduler.paused')}
              </span>
            )}
          </div>

          {friendlyDesc && (
            <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
              {friendlyDesc}
            </p>
          )}

          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-muted)]">
            <span>
              <span className="text-[var(--text-secondary)]">
                {triggerLabel(job, t)}
              </span>
            </span>
            <span>
              {t('scheduler.last_run')}:{' '}
              <span className="text-[var(--text-secondary)]">
                {relativeTime(job.last_run?.finished_at ?? null, t)}
              </span>
            </span>
            <span>
              {t('scheduler.next_run')}:{' '}
              <span className="text-[var(--text-secondary)]">
                {relativeTime(job.next_run_time, t)}
              </span>
            </span>
          </div>

          <div className="mt-2 flex items-center gap-3">
            <div style={{ width: '180px', maxWidth: '40%' }}>
              <HealthBar stats={job.stats_7d} />
            </div>
            <span className="text-[11px] text-[var(--text-muted)]">
              {t('scheduler.health_summary', {
                ok: job.stats_7d.ok,
                err: job.stats_7d.error,
                defaultValue: `${job.stats_7d.ok} ok · ${job.stats_7d.error} err (7d)`,
              })}
            </span>
          </div>
        </div>

        {/* Right column: primary action + kebab */}
        <div className="flex flex-shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={handleRunNow}
            disabled={mut.runNow.isPending}
            aria-label={t('scheduler.run_now')}
            className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[12px] font-medium text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Play size={13} />
            <span className="hidden sm:inline">{t('scheduler.run_now')}</span>
          </button>
          <KebabMenu
            ariaLabel={t('scheduler.actions_menu', {
              defaultValue: 'Actions',
            })}
            items={[
              {
                key: 'pauseresume',
                label: job.paused
                  ? t('scheduler.resume')
                  : t('scheduler.pause'),
                icon: job.paused ? <Play size={14} /> : <Pause size={14} />,
                onClick: handlePauseResume,
                disabled: mut.pause.isPending || mut.resume.isPending,
              },
              {
                key: 'edit',
                label: t('scheduler.edit_trigger'),
                icon: <Edit3 size={14} />,
                onClick: () => setEditOpen(true),
              },
              {
                key: 'history',
                label: t('scheduler.history'),
                icon: <History size={14} />,
                onClick: onOpenHistory,
              },
              {
                key: 'reset',
                label: t('scheduler.reset_default'),
                icon: <RotateCcw size={14} />,
                onClick: handleReset,
                disabled:
                  job.trigger_is_default || mut.resetDefault.isPending,
              },
            ]}
          />
        </div>
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
    </>
  )
}
