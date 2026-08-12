import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { JobRow } from '../JobRow'
import type { SchedulerJob } from '@/lib/types'

// i18n mock — returns the key plus its interpolated count, so a test can tell
// "in {{n}} h" from "{{n}} h ago" without depending on the translated wording.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return String(opts.defaultValue ?? k)
      }
      if (opts && typeof opts === 'object' && 'n' in opts) return `${k}:${String(opts.n)}`
      return k
    },
  }),
}))

const idleMutation = () => ({ mutate: vi.fn(), isPending: false, error: null })
vi.mock('@/hooks/useSchedulerMutations', () => ({
  useSchedulerMutations: () => ({
    runNow: idleMutation(),
    pause: idleMutation(),
    resume: idleMutation(),
    patchTrigger: idleMutation(),
    resetDefault: idleMutation(),
  }),
}))

const NOW = new Date('2026-08-12T18:00:00.000Z')

const makeJob = (over: Partial<SchedulerJob> = {}): SchedulerJob => ({
  id: 'wanted_scanner',
  description: 'Scans the library.',
  owner_module: '',
  trigger: { type: 'interval', hours: 6 },
  trigger_is_default: true,
  paused: false,
  next_run_time: null,
  last_run: null,
  stats_7d: { ok: 4, error: 0, timeout: 0, missed: 0, skipped_overlap: 0 },
  ...over,
})

describe('JobRow — relative times', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders a future next run as future, not as the past', () => {
    // Regression: the helper took Math.abs(diff) and always formatted with the
    // past-tense strings, so every scheduled job read "2 h ago" — including one
    // that had just run and was due again in two minutes.
    render(
      <JobRow
        job={makeJob({ next_run_time: '2026-08-12T19:30:00.000Z' })}
        onOpenHistory={() => {}}
      />,
    )

    expect(screen.getByText(/scheduler\.in_hours:2/)).toBeInTheDocument()
    expect(screen.queryByText(/hours_ago/)).not.toBeInTheDocument()
  })

  it('still renders a past last run as the past', () => {
    render(
      <JobRow
        job={makeJob({
          last_run: {
            status: 'ok',
            started_at: '2026-08-12T14:00:00.000Z',
            finished_at: '2026-08-12T14:01:00.000Z',
            duration_ms: 60_000,
          } as SchedulerJob['last_run'],
        })}
        onOpenHistory={() => {}}
      />,
    )

    expect(screen.getByText(/scheduler\.hours_ago:4/)).toBeInTheDocument()
  })

  it('says a run is due rather than claiming it just happened', () => {
    render(
      <JobRow
        job={makeJob({ next_run_time: '2026-08-12T18:00:30.000Z' })}
        onOpenHistory={() => {}}
      />,
    )

    expect(screen.getByText(/scheduler\.due_now/)).toBeInTheDocument()
    expect(screen.queryByText(/just_now/)).not.toBeInTheDocument()
  })
})
