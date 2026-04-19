import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

const mockJob = {
  id: 'scheduler_history_cleanup',
  description: 'Delete old rows',
  owner_module: 'services.scheduler',
  trigger: { type: 'cron' as const, hour: '3', minute: '15' },
  trigger_is_default: true,
  paused: false,
  next_run_time: '2026-04-19T03:15:00Z',
  last_run: null,
  stats_7d: { ok: 0, error: 0, timeout: 0, missed: 0, skipped_overlap: 0 },
}

vi.mock('@/hooks/useSchedulerJobs', () => ({
  useSchedulerJobs: () => ({
    data: { jobs: [mockJob] },
    isLoading: false,
    error: null,
  }),
  useSchedulerJob: () => ({ data: undefined, isLoading: false, error: null }),
}))

vi.mock('@/hooks/useSchedulerJobRuns', () => ({
  useSchedulerJobRuns: () => ({
    data: { total: 0, limit: 50, offset: 0, runs: [] },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (opts && typeof opts === 'object' && 'defaultValue' in opts) {
        return (opts.defaultValue as string) ?? key
      }
      return key
    },
  }),
}))

const { SchedulerPage } = await import('../SchedulerPage')

function renderPage() {
  return render(
    <MemoryRouter>
      <SchedulerPage />
    </MemoryRouter>,
  )
}

describe('SchedulerPage', () => {
  it('renders job cards', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('scheduler_history_cleanup')).toBeInTheDocument(),
    )
  })

  it('disables write action buttons with phase3 tooltip', async () => {
    renderPage()
    await waitFor(() => screen.getByText('scheduler_history_cleanup'))

    // Run now, Pause, Edit trigger, Reset default are all Phase 3 and must be disabled.
    const runBtn = screen.getByRole('button', { name: /scheduler\.run_now/i })
    const pauseBtn = screen.getByRole('button', { name: /scheduler\.pause/i })
    const editBtn = screen.getByRole('button', { name: /scheduler\.edit_trigger/i })
    const resetBtn = screen.getByRole('button', { name: /scheduler\.reset_default/i })

    expect(runBtn).toBeDisabled()
    expect(pauseBtn).toBeDisabled()
    expect(editBtn).toBeDisabled()
    expect(resetBtn).toBeDisabled()

    // Tooltip / title points to Phase 3.
    expect(runBtn).toHaveAttribute('title', 'scheduler.phase3_coming')

    // History is the one active button — not disabled.
    const historyBtn = screen.getByRole('button', { name: /scheduler\.history/i })
    expect(historyBtn).not.toBeDisabled()
  })
})
