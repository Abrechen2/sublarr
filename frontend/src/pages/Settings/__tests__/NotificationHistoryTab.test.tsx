import { render, screen, waitFor } from '@testing-library/react'
import { vi, it, expect, describe } from 'vitest'

const mockResend = vi.fn()
let mockEntries: unknown[] = []

vi.mock('@/hooks/useSystemApi', () => ({
  useNotificationHistory: () => ({
    data: { entries: mockEntries, total_pages: 1 },
    isLoading: false,
  }),
  useResendNotification: () => ({ mutate: mockResend, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

const { NotificationHistoryTab } = await import('../NotificationHistoryTab')

describe('NotificationHistoryTab', () => {
  it('renders table with notification rows', async () => {
    mockEntries = [
      { id: 1, timestamp: '2026-03-21T10:00:00Z', event_type: 'subtitle_found', channel: 'discord', status: 'sent' },
    ]
    render(<NotificationHistoryTab />)
    await waitFor(() => expect(screen.getByText('subtitle_found')).toBeInTheDocument())
  })

  it('renders resend button per row', async () => {
    mockEntries = [
      { id: 1, timestamp: '2026-03-21T10:00:00Z', event_type: 'subtitle_found', channel: 'discord', status: 'sent' },
    ]
    render(<NotificationHistoryTab />)
    await waitFor(() =>
      expect(screen.getAllByRole('button', { name: /resend/i }).length).toBeGreaterThan(0)
    )
  })

  it('shows empty state when no history', () => {
    mockEntries = []
    render(<NotificationHistoryTab />)
    expect(screen.getByTestId('history-empty')).toBeInTheDocument()
  })
})
