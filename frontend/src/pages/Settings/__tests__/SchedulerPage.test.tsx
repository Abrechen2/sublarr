import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

describe('SchedulerPage (grouped redesign)', () => {
  it('renders the job inside its category section', async () => {
    renderPage()
    await waitFor(() =>
      expect(
        screen.getByTestId('scheduler-job-row-scheduler_history_cleanup'),
      ).toBeInTheDocument(),
    )
    // Maintenance group must exist (cleanup-class job).
    expect(
      screen.getByTestId('scheduler-group-maintenance'),
    ).toBeInTheDocument()
  })

  it('shows Run Now as a primary visible button', async () => {
    renderPage()
    await waitFor(() =>
      screen.getByTestId('scheduler-job-row-scheduler_history_cleanup'),
    )
    const runBtn = screen.getByRole('button', { name: /scheduler\.run_now/i })
    expect(runBtn).not.toBeDisabled()
  })

  it('exposes Pause / Edit / History / Reset via the kebab menu', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() =>
      screen.getByTestId('scheduler-job-row-scheduler_history_cleanup'),
    )

    // KebabMenu button uses defaultValue 'Actions' / 'More actions' for
    // its aria-label, so the i18n mock returns that string directly.
    const kebab = screen.getByRole('button', { name: /actions/i })
    await user.click(kebab)

    const pauseItem = screen.getByRole('menuitem', { name: /scheduler\.pause/i })
    const editItem = screen.getByRole('menuitem', { name: /scheduler\.edit_trigger/i })
    const historyItem = screen.getByRole('menuitem', { name: /scheduler\.history/i })
    const resetItem = screen.getByRole('menuitem', { name: /scheduler\.reset_default/i })

    expect(pauseItem).not.toBeDisabled()
    expect(editItem).not.toBeDisabled()
    expect(historyItem).not.toBeDisabled()
    // Reset is disabled while the job still uses its default trigger
    // (mockJob.trigger_is_default === true).
    expect(resetItem).toBeDisabled()
  })
})
