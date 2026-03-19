import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AutomationWidget } from '../components/dashboard/widgets/AutomationWidget'

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

const mockSummary = {
  wanted_count: 12, found_today: 8, failed_today: 2,
  last_search_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
}

describe('AutomationWidget', () => {
  it('renders Active badge when enabled', () => {
    render(<AutomationWidget enabled intervalHours={6} summary={mockSummary} onRunNow={vi.fn()} isRunning={false} />, { wrapper })
    expect(screen.getByText(/active/i)).toBeInTheDocument()
  })

  it('renders Disabled badge when not enabled', () => {
    render(<AutomationWidget enabled={false} intervalHours={6} summary={mockSummary} onRunNow={vi.fn()} isRunning={false} />, { wrapper })
    expect(screen.getByText(/disabled/i)).toBeInTheDocument()
  })

  it('shows found_today count', () => {
    render(<AutomationWidget enabled intervalHours={6} summary={mockSummary} onRunNow={vi.fn()} isRunning={false} />, { wrapper })
    expect(screen.getByText('8')).toBeInTheDocument()
  })

  it('calls onRunNow on button click', async () => {
    const user = userEvent.setup()
    const fn = vi.fn()
    render(<AutomationWidget enabled intervalHours={6} summary={mockSummary} onRunNow={fn} isRunning={false} />, { wrapper })
    await user.click(screen.getByRole('button', { name: /run now/i }))
    expect(fn).toHaveBeenCalledOnce()
  })

  it('disables button while running', () => {
    render(<AutomationWidget enabled intervalHours={6} summary={mockSummary} onRunNow={vi.fn()} isRunning />, { wrapper })
    expect(screen.getByRole('button', { name: /searching/i })).toBeDisabled()
  })
})
