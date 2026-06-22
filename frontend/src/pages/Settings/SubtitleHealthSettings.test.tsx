import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SubtitleHealthSettings } from './SubtitleHealthSettings'
import * as api from '@/api/subtitleHealth'

vi.mock('@/api/subtitleHealth')
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: any) => (o ? `${k} ${JSON.stringify(o)}` : k) }),
}))

describe('SubtitleHealthSettings', () => {
  it('renders the library report', async () => {
    vi.mocked(api.getHealthReport).mockResolvedValue({
      total_findings: 47,
      by_type: { ass_escape_leak: 46, language_mislabel: 1 },
      affected_episodes: 23,
    })
    render(<SubtitleHealthSettings />)
    await waitFor(() =>
      expect(screen.getByText(/subtitle_health.report_total/)).toBeInTheDocument(),
    )
  })
})
