/**
 * Schedule presets for the `foreign_track_sweep` scheduler job, and the
 * per-run budget bounds (1.15.0-rc.5, owner request 2026-09-26: the sweep's
 * pace must be configurable).
 *
 * The preset is never stored: it is read back from the job's live trigger, so
 * an edit made on the Scheduler page shows up here as "custom" rather than as
 * a stale choice.
 */
import type { Trigger } from '@/lib/types'

export type SweepPreset = 'every6h' | 'hourly' | 'nightly' | 'custom'

export const SWEEP_JOB_ID = 'foreign_track_sweep'

/** Cron hours of the nightly window: fires 01:00 … 06:00, runs end by ~07:00. */
export const NIGHTLY_HOURS = '1-6'

const SIX_HOURS_S = 6 * 3600
const ONE_HOUR_S = 3600

/** Mirror of `foreign_track_sweep_budget_s` Field(ge=300, le=3600). */
export const BUDGET_MIN_MINUTES = 5
export const BUDGET_MAX_MINUTES = 60

const CRON_FIELDS = ['year', 'month', 'day', 'week', 'day_of_week', 'hour', 'minute', 'second'] as const

export function detectSweepPreset(trigger: Trigger | undefined): SweepPreset {
  if (!trigger) return 'custom'
  if (trigger.type === 'interval') {
    const seconds =
      (trigger.seconds ?? 0) + (trigger.minutes ?? 0) * 60 + (trigger.hours ?? 0) * 3600
    if (seconds === SIX_HOURS_S) return 'every6h'
    if (seconds === ONE_HOUR_S) return 'hourly'
    return 'custom'
  }
  const setFields = CRON_FIELDS.filter((f) => trigger[f] !== undefined && trigger[f] !== null)
  const onlyHourMinute =
    setFields.length === 2 && setFields.includes('hour') && setFields.includes('minute')
  if (onlyHourMinute && String(trigger.hour) === NIGHTLY_HOURS && String(trigger.minute) === '0') {
    return 'nightly'
  }
  return 'custom'
}

/**
 * The trigger a preset PATCHes. `every6h` has none: it resets the job to its
 * code default instead, so the Scheduler page shows it as "default" again.
 */
export function presetTrigger(preset: SweepPreset, timeZone: string): Trigger | null {
  switch (preset) {
    case 'hourly':
      return { type: 'interval', hours: 1 }
    case 'nightly':
      return { type: 'cron', hour: NIGHTLY_HOURS, minute: '0', timezone: timeZone }
    default:
      return null
  }
}

/** Minutes typed into the budget field → seconds for the config, clamped. */
export function budgetMinutesToSeconds(minutes: number): number | null {
  if (!Number.isFinite(minutes)) return null
  const clamped = Math.min(BUDGET_MAX_MINUTES, Math.max(BUDGET_MIN_MINUTES, Math.round(minutes)))
  return clamped * 60
}

/** The browser's IANA zone, e.g. "Europe/Berlin"; UTC when unavailable. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}
