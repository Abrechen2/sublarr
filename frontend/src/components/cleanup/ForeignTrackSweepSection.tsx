/**
 * ForeignTrackSweepSection — pace controls for the automatic foreign-track
 * sweep, shown inside the foreign_tracks cleanup card (1.15.0-rc.5).
 *
 * Prod 2026-09-26 stripped ~1.6 GB/min with 38.5 TiB queued, which at the
 * default (every 6 h, 30 min per run) is months. The owner asked for the pace
 * to be configurable. Every value here has exactly one home:
 *   on/off, budget      → global config (PUT /config)
 *   schedule            → the `foreign_track_sweep` scheduler job's trigger
 *   backup retention    → global config, edited on the Remux page (read here)
 *   progress            → GET /statistics/foreign-tracks
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { useSchedulerJob } from '@/hooks/useSchedulerJobs'
import { useSchedulerMutations } from '@/hooks/useSchedulerMutations'
import { useStatForeignTracks } from '@/hooks/useStatistics'
import { Toggle } from '@/components/shared/Toggle'
import { toast } from '@/components/shared/Toast'
import { boolVal, numVal } from '@/lib/configUtils'
import type { Trigger } from '@/lib/types'
import {
  BUDGET_MAX_MINUTES,
  BUDGET_MIN_MINUTES,
  SWEEP_JOB_ID,
  browserTimeZone,
  budgetMinutesToSeconds,
  detectSweepPreset,
  presetTrigger,
  type SweepPreset,
} from './sweepSchedule'

const SCHEDULER_PAGE = '/settings/system/scheduler'
const REMUX_PAGE = '/settings/subtitles/stream-management'
const DEFAULT_BUDGET_S = 1800
const DEFAULT_RETENTION_DAYS = 7
const PRESETS: SweepPreset[] = ['every6h', 'hourly', 'nightly', 'custom']

type TFn = (key: string, opts?: Record<string, unknown>) => string

function describeTrigger(trigger: Trigger, t: TFn): string {
  if (trigger.type === 'interval') {
    const s = trigger.seconds ?? 0
    if (s >= 3600 && s % 3600 === 0) return t('cleanup_card.sweep.every_hours', { n: s / 3600 })
    return t('cleanup_card.sweep.every_minutes', { n: Math.round(s / 60) })
  }
  return t('cleanup_card.sweep.cron', {
    hour: trigger.hour ?? '*',
    minute: trigger.minute ?? '*',
    tz: trigger.timezone ?? 'UTC',
  })
}

function isConflict(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 409
}

const sectionLabel = 'text-[10px] font-semibold uppercase tracking-wider mb-2 text-muted'
const hintText = 'text-[11px] mt-1.5 text-muted leading-snug'
const inputClass =
  'px-3 py-2 rounded-lg text-sm focus:outline-none bg-surface border border-border text-foreground'

export function ForeignTrackSweepSection({ ruleEnabled }: { ruleEnabled: boolean }) {
  const { t } = useTranslation('common')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const jobQuery = useSchedulerJob(SWEEP_JOB_ID)
  const mut = useSchedulerMutations(SWEEP_JOB_ID)
  const { data: stats } = useStatForeignTracks()

  const sweepEnabled = boolVal(config, 'foreign_track_sweep_enabled', false)
  const budgetS = numVal(config, 'foreign_track_sweep_budget_s', DEFAULT_BUDGET_S)
  const retentionDays = numVal(config, 'remux_backup_retention_days', DEFAULT_RETENTION_DAYS)

  const [budgetDraft, setBudgetDraft] = useState(String(Math.round(budgetS / 60)))
  useEffect(() => {
    setBudgetDraft(String(Math.round(budgetS / 60)))
  }, [budgetS])

  const job = jobQuery.data
  const preset = detectSweepPreset(job?.trigger)
  const tz = browserTimeZone()

  const save = (values: Record<string, unknown>) =>
    updateConfig.mutate(values, {
      onSuccess: () => toast(t('cleanup_card.sweep.saved'), 'success'),
      onError: () => toast(t('cleanup_card.sweep.save_failed'), 'error'),
    })

  const commitBudget = () => {
    const seconds = budgetMinutesToSeconds(parseInt(budgetDraft, 10))
    if (seconds === null) {
      setBudgetDraft(String(Math.round(budgetS / 60)))
      return
    }
    setBudgetDraft(String(seconds / 60))
    if (seconds !== budgetS) save({ foreign_track_sweep_budget_s: seconds })
  }

  const scheduleCallbacks = {
    onSuccess: () => toast(t('cleanup_card.sweep.schedule_saved'), 'success'),
    onError: () => toast(t('cleanup_card.sweep.schedule_failed'), 'error'),
  }

  const choosePreset = (next: SweepPreset) => {
    if (next === preset || next === 'custom') return
    const trigger = presetTrigger(next, tz)
    if (trigger === null) mut.resetDefault.mutate(undefined, scheduleCallbacks)
    else mut.patchTrigger.mutate(trigger, scheduleCallbacks)
  }

  const runNow = () =>
    mut.runNow.mutate(undefined, {
      onSuccess: () => toast(t('cleanup_card.sweep.queued'), 'success'),
      onError: (err) =>
        isConflict(err)
          ? toast(t('cleanup_card.sweep.already_pending'), 'info')
          : toast(t('cleanup_card.sweep.run_failed'), 'error'),
    })

  const scheduleBusy = mut.patchTrigger.isPending || mut.resetDefault.isPending

  return (
    <section className="mt-5 pt-5 border-t border-border" aria-label={t('cleanup_card.sweep.title')}>
      <div className="flex items-center justify-between gap-3 mb-1">
        <div className="text-sm font-semibold text-foreground">{t('cleanup_card.sweep.title')}</div>
        <label className="flex items-center gap-2 text-xs text-secondary">
          {sweepEnabled ? t('cleanup_card.active') : t('cleanup_card.inactive')}
          <Toggle
            checked={sweepEnabled}
            onChange={(v) => save({ foreign_track_sweep_enabled: v })}
            disabled={config === undefined}
          />
        </label>
      </div>
      <p className="text-xs text-muted mb-4">{t('cleanup_card.sweep.intro')}</p>
      {sweepEnabled && !ruleEnabled && (
        <p className="text-xs mb-4 text-warning">{t('cleanup_card.sweep.rule_inactive')}</p>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        {/* Schedule */}
        <div>
          <div className={sectionLabel}>{t('cleanup_card.sweep.schedule')}</div>
          {jobQuery.isError ? (
            <p className="text-xs text-muted">{t('cleanup_card.sweep.scheduler_unavailable')}</p>
          ) : (
            <>
              <select
                data-testid="sweep-preset"
                value={preset}
                disabled={!job || scheduleBusy}
                onChange={(e) => choosePreset(e.target.value as SweepPreset)}
                className={`${inputClass} w-full max-w-xs`}
              >
                {PRESETS.map((p) => (
                  <option key={p} value={p} disabled={p === 'custom'}>
                    {t(`cleanup_card.sweep.preset.${p}`)}
                  </option>
                ))}
              </select>
              {job && (
                <div className={hintText}>
                  <div>{t('cleanup_card.sweep.current', { trigger: describeTrigger(job.trigger, t) })}</div>
                  <div data-testid="sweep-next-run">
                    {job.paused
                      ? t('cleanup_card.sweep.job_paused')
                      : t('cleanup_card.sweep.next_run', {
                          date: job.next_run_time
                            ? new Date(job.next_run_time).toLocaleString()
                            : '—',
                        })}
                  </div>
                </div>
              )}
              {preset === 'nightly' && (
                <p className={hintText}>
                  {t('cleanup_card.sweep.nightly_hint', {
                    tz: job?.trigger.type === 'cron' ? (job.trigger.timezone ?? 'UTC') : tz,
                  })}
                </p>
              )}
              {preset === 'custom' && job && (
                <p className={hintText}>
                  {t('cleanup_card.sweep.custom_hint')}{' '}
                  <Link to={SCHEDULER_PAGE} className="underline text-accent">
                    {t('cleanup_card.sweep.open_scheduler')}
                  </Link>
                </p>
              )}
            </>
          )}
        </div>

        {/* Budget */}
        <div>
          <div className={sectionLabel}>{t('cleanup_card.sweep.budget')}</div>
          <input
            data-testid="sweep-budget"
            type="number"
            min={BUDGET_MIN_MINUTES}
            max={BUDGET_MAX_MINUTES}
            value={budgetDraft}
            disabled={config === undefined}
            onChange={(e) => setBudgetDraft(e.target.value)}
            onBlur={commitBudget}
            className={`${inputClass} w-[110px]`}
          />
          <p className={hintText}>
            {t('cleanup_card.sweep.budget_hint', {
              min: BUDGET_MIN_MINUTES,
              max: BUDGET_MAX_MINUTES,
            })}
          </p>
        </div>

        {/* Backup retention (edited on the Remux page) */}
        <div className="sm:col-span-2">
          <div className={sectionLabel}>{t('cleanup_card.sweep.retention')}</div>
          <div className="text-sm text-foreground">
            {retentionDays === 0
              ? t('cleanup_card.sweep.retention_forever')
              : t('cleanup_card.sweep.retention_value', { count: retentionDays })}{' '}
            <Link to={REMUX_PAGE} className="text-xs underline text-accent">
              {t('cleanup_card.sweep.retention_link')}
            </Link>
          </div>
          <p className={hintText}>{t('cleanup_card.sweep.retention_hint')}</p>
        </div>
      </div>

      {/* Progress + run now */}
      <div className="flex flex-wrap items-center gap-3 mt-4">
        <button
          type="button"
          onClick={runNow}
          disabled={!sweepEnabled || mut.runNow.isPending}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium disabled:opacity-40 border border-border text-secondary"
          title={sweepEnabled ? undefined : t('cleanup_card.sweep.enable_first')}
        >
          <Play size={12} />
          {t('cleanup_card.sweep.run_now')}
        </button>
        {stats && (
          <span data-testid="sweep-progress" className="text-xs text-muted">
            {t('cleanup_card.sweep.progress', {
              affected: stats.scan_counts.affected.toLocaleString(),
              pending: stats.scan_counts.pending.toLocaleString(),
              stripped: stats.files_stripped.toLocaleString(),
            })}
            {' · '}
            {t('cleanup_card.sweep.phase', {
              phase: t(`track_cleanup.phase.${stats.phase}`, { ns: 'statistics' }),
            })}
            {stats.paused_reason &&
              ` · ${t('cleanup_card.sweep.paused_reason', {
                reason: t(`sweep_pause.${stats.paused_code ?? 'unknown'}`, {
                  defaultValue: stats.paused_reason,
                }),
              })}`}
          </span>
        )}
      </div>
    </section>
  )
}
