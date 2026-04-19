import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

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

vi.mock('@/components/settings/SettingsDetailLayout', () => ({
  SettingsDetailLayout: ({
    title,
    subtitle,
    children,
  }: {
    title: string
    subtitle: string
    children: React.ReactNode
  }) => (
    <div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
      {children}
    </div>
  ),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

vi.mock('@/api/translation', () => ({
  getQueue: vi.fn().mockResolvedValue({
    active: [
      {
        job_id: 'abc123',
        file_path: '/media/movie.mkv',
        source_lang: 'en',
        target_lang: 'de',
        backend: 'claude',
        progress: { done: 50, total: 100, pct: 50.0 },
        started_at: '2026-04-19T10:00:00Z',
        eta_seconds: 30,
        cost_so_far_micro_usd: 12400,
        cancel_requested: false,
      },
    ],
    recent: [
      {
        job_id: 'def456',
        file_path: '/media/show.s01e01.mkv',
        source_lang: 'en',
        target_lang: 'de',
        backend: 'ollama',
        lines: 428,
        status: 'ok',
        error_type: null,
        finished_at: '2026-04-19T09:55:00Z',
        duration_s: 12.5,
        cost_micro_usd: 0,
      },
    ],
  }),
  cancelJob: vi.fn(),
}))

const { QueueDashboard } = await import('../QueueDashboard')

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <QueueDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('QueueDashboard', () => {
  it('renders active job with progress', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('movie.mkv')).toBeInTheDocument()
    })
    expect(screen.getByText(/50\/100/)).toBeInTheDocument()
    expect(screen.getByText(/50\.0%/)).toBeInTheDocument()
  })

  it('renders recent job with status and metadata', async () => {
    renderPage()
    await waitFor(() => {
      expect(screen.getByText('show.s01e01.mkv')).toBeInTheDocument()
    })
    expect(screen.getByText(/12\.5s/)).toBeInTheDocument()
    expect(screen.getByText(/428 lines/)).toBeInTheDocument()
  })

  it('shows cancel button on active jobs', async () => {
    renderPage()
    await waitFor(() => screen.getByText('movie.mkv'))
    const buttons = screen.getAllByRole('button')
    const cancelButton = buttons.find((btn) =>
      btn.textContent?.includes('translation.queue.cancel'),
    )
    expect(cancelButton).toBeInTheDocument()
    expect(cancelButton).not.toBeDisabled()
  })
})
