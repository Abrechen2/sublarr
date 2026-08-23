/**
 * Every skip reason the backend can emit must have a label here.
 *
 * The reasons are enumerated by hand on both sides: `decision_log.provider_skipped`
 * in the backend chooses the string, and PROVIDER_SKIP_KEYS plus the two locale
 * files translate it. Nothing links them, so a reason added in the backend
 * renders in the decision log as a raw key like `language_unsupported` — on the
 * screen someone opens precisely to find out why a provider did nothing.
 *
 * This is the second time that gap has been found by looking at a rendered page
 * rather than by a test (the first was the scheduler's `timeout_not_started`),
 * which is why it is pinned here.
 */
import { describe, expect, it } from 'vitest'
import { PROVIDER_SKIP_KEYS } from '../DecisionLogModal'
import de from '@/i18n/locales/de/activity.json'
import en from '@/i18n/locales/en/activity.json'

/** Kept in step with `decision_log.provider_skipped` call sites in the backend. */
const BACKEND_SKIP_REASONS = [
  'auto_disabled',
  'circuit_open',
  'rate_limited',
  'budget_exhausted',
  'no_pool_key',
  'languages_excluded',
  'language_unsupported',
  'not_applicable',
] as const

const lookup = (bundle: unknown, dotted: string) =>
  dotted.split('.').reduce<any>((acc, part) => (acc == null ? acc : acc[part]), bundle)

describe('decision-log skip reasons', () => {
  it.each(BACKEND_SKIP_REASONS)('%s is mapped to a translation key', (reason) => {
    expect(
      PROVIDER_SKIP_KEYS[reason],
      `no mapping for "${reason}" — the decision log would show the raw key`,
    ).toBeTruthy()
  })

  it.each(BACKEND_SKIP_REASONS)('%s has a German label', (reason) => {
    const key = PROVIDER_SKIP_KEYS[reason]
    expect(lookup(de, key), `missing de label for ${key}`).toBeTruthy()
  })

  it.each(BACKEND_SKIP_REASONS)('%s has an English label', (reason) => {
    const key = PROVIDER_SKIP_KEYS[reason]
    expect(lookup(en, key), `missing en label for ${key}`).toBeTruthy()
  })

  it('keeps the two locales in step', () => {
    const deKeys = Object.keys((de as Record<string, any>).decision).sort()
    const enKeys = Object.keys((en as Record<string, any>).decision).sort()
    expect(deKeys).toEqual(enKeys)
  })
})
