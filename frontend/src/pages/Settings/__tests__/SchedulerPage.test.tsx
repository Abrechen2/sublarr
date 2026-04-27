import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

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
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SchedulerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('SchedulerPage', () => {
  it('renders job cards', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText('scheduler_history_cleanup')).toBeInTheDocument(),
    )
  })

  it('write actions are enabled; reset is disabled when trigger is default', async () => {
    renderPage()
    await waitFor(() => screen.getByText('scheduler_history_cleanup'))

    // Phase 3 mutations are wired up — Run/Pause/Edit/History are interactive.
    const runBtn = screen.getByRole('button', { name: /scheduler\.run_now/i })
    const pauseBtn = screen.getByRole('button', { name: /scheduler\.pause/i })
    const editBtn = screen.getByRole('button', { name: /scheduler\.edit_trigger/i })
    const historyBtn = screen.getByRole('button', { name: /scheduler\.history/i })
    expect(runBtn).not.toBeDisabled()
    expect(pauseBtn).not.toBeDisabled()
    expect(editBtn).not.toBeDisabled()
    expect(historyBtn).not.toBeDisabled()

    // Reset-default is disabled while the job still uses its default trigger
    // (mockJob.trigger_is_default === true).
    const resetBtn = screen.getByRole('button', { name: /scheduler\.reset_default/i })
    expect(resetBtn).toBeDisabled()
  })
})
