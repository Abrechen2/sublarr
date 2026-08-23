/**
 * Every scheduler status the backend can emit must be renderable here.
 *
 * The backend added `timeout_not_started` and this file did not know it: the
 * union, the colour map, the history filter and both locales all enumerate the
 * statuses by hand, so a new one renders unstyled and untranslated. Nothing in
 * tsc or the backend suite catches that — it was found by looking at the
 * rendered page during UAT.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../StatusBadge'
import type { SchedulerStatus } from '@/types/system'
import de from '@/i18n/locales/de/settings.json'
import en from '@/i18n/locales/en/settings.json'

// Kept in step with SchedulerStatus by the type assertion below: adding a
// member to the union without adding it here stops compiling.
const ALL_STATUSES = [
  'ok',
  'error',
  'timeout',
  'timeout_abandoned',
  'timeout_not_started',
  'missed',
  'skipped_overlap',
] as const satisfies readonly SchedulerStatus[]

type Covered = (typeof ALL_STATUSES)[number]
// Fails to compile if the union grows and this list does not.
const _exhaustive: Record<SchedulerStatus, true> = Object.fromEntries(
  ALL_STATUSES.map((s) => [s, true]),
) as Record<Covered, true>
void _exhaustive

describe('scheduler run statuses', () => {
  it.each(ALL_STATUSES)('renders a badge for %s', (status) => {
    render(<StatusBadge status={status} />)
    expect(screen.getByLabelText(`Status: ${status}`)).toBeInTheDocument()
  })

  it.each(ALL_STATUSES)('has a German label for %s', (status) => {
    expect(
      (de as Record<string, any>).scheduler?.status?.[status],
      `missing de label for ${status} — it would render as the raw key`,
    ).toBeTruthy()
  })

  it.each(ALL_STATUSES)('has an English label for %s', (status) => {
    expect(
      (en as Record<string, any>).scheduler?.status?.[status],
      `missing en label for ${status} — it would render as the raw key`,
    ).toBeTruthy()
  })

  it('keeps the two locales in step', () => {
    const deKeys = Object.keys((de as Record<string, any>).scheduler.status).sort()
    const enKeys = Object.keys((en as Record<string, any>).scheduler.status).sort()
    expect(deKeys).toEqual(enKeys)
  })
})
