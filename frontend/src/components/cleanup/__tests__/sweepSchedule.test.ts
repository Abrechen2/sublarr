import { describe, it, expect } from 'vitest'
import {
  NIGHTLY_HOURS,
  detectSweepPreset,
  presetTrigger,
  budgetMinutesToSeconds,
  BUDGET_MIN_MINUTES,
  BUDGET_MAX_MINUTES,
} from '../sweepSchedule'

describe('detectSweepPreset', () => {
  it('reads a 6 h interval as the default preset', () => {
    expect(detectSweepPreset({ type: 'interval', seconds: 21600 })).toBe('every6h')
  })

  it('reads a 1 h interval as hourly', () => {
    expect(detectSweepPreset({ type: 'interval', seconds: 3600 })).toBe('hourly')
  })

  it('reads the nightly cron in any time zone as nightly', () => {
    expect(
      detectSweepPreset({ type: 'cron', hour: '1-6', minute: '0', timezone: 'Europe/Berlin' }),
    ).toBe('nightly')
    expect(detectSweepPreset({ type: 'cron', hour: '1-6', minute: '0', timezone: 'UTC' })).toBe(
      'nightly',
    )
  })

  it('reads anything else as custom', () => {
    expect(detectSweepPreset({ type: 'interval', seconds: 7200 })).toBe('custom')
    expect(detectSweepPreset({ type: 'cron', hour: '1-6', minute: '30' })).toBe('custom')
    expect(
      detectSweepPreset({ type: 'cron', hour: '1-6', minute: '0', day_of_week: 'sat' }),
    ).toBe('custom')
    expect(detectSweepPreset(undefined)).toBe('custom')
  })
})

describe('presetTrigger', () => {
  it('builds the hourly interval', () => {
    expect(presetTrigger('hourly', 'Europe/Berlin')).toEqual({ type: 'interval', hours: 1 })
  })

  it('builds the nightly cron in the given zone', () => {
    expect(presetTrigger('nightly', 'Europe/Berlin')).toEqual({
      type: 'cron',
      hour: NIGHTLY_HOURS,
      minute: '0',
      timezone: 'Europe/Berlin',
    })
  })

  it('has no trigger for the default preset (it resets to the job default)', () => {
    expect(presetTrigger('every6h', 'UTC')).toBeNull()
  })

  it('round-trips: what a preset sends is detected as that preset', () => {
    // The server reports an interval in seconds and a cron with its fields as strings.
    expect(detectSweepPreset({ type: 'interval', seconds: 3600 })).toBe('hourly')
    const nightly = presetTrigger('nightly', 'Europe/Berlin')
    expect(nightly && detectSweepPreset(nightly)).toBe('nightly')
  })
})

describe('budgetMinutesToSeconds', () => {
  it('clamps into the server bounds', () => {
    expect(budgetMinutesToSeconds(30)).toBe(1800)
    expect(budgetMinutesToSeconds(1)).toBe(BUDGET_MIN_MINUTES * 60)
    expect(budgetMinutesToSeconds(500)).toBe(BUDGET_MAX_MINUTES * 60)
    expect(budgetMinutesToSeconds(Number.NaN)).toBeNull()
  })

  it('matches the backend Field bounds (300..3600 s)', () => {
    expect(BUDGET_MIN_MINUTES * 60).toBe(300)
    expect(BUDGET_MAX_MINUTES * 60).toBe(3600)
  })
})
