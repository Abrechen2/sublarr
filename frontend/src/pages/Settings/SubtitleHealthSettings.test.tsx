import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { SubtitleHealthSettings } from './SubtitleHealthSettings'
import * as api from '@/api/subtitleHealth'

vi.mock('@/api/subtitleHealth')
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: any) => (o ? `${k} ${JSON.stringify(o)}` : k) }),
}))

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AdvancedSettingsProvider>{ui}</AdvancedSettingsProvider>
    </QueryClientProvider>,
  )
}

describe('SubtitleHealthSettings', () => {
  it('renders the library report', async () => {
    vi.mocked(api.getHealthReport).mockResolvedValue({
      total_findings: 47,
      by_type: { ass_escape_leak: 46, language_mislabel: 1 },
      affected_episodes: 23,
    })
    renderWithQuery(<SubtitleHealthSettings />)
    await waitFor(() =>
      expect(screen.getByText(/subtitle_health.report_total/)).toBeInTheDocument(),
    )
  })

  it('renders the AI quality section', async () => {
    vi.mocked(api.getHealthReport).mockResolvedValue({
      total_findings: 0,
      by_type: {},
      affected_episodes: 0,
    })
    renderWithQuery(<SubtitleHealthSettings />)
    await waitFor(() => expect(screen.getByTestId('toggle-ai-quality')).toBeInTheDocument())
  })
})
