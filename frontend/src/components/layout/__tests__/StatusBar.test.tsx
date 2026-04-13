import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useUpdateInfo } from '@/hooks/useApi'
import { useProviderHealth } from '@/hooks/useProvidersApi'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/hooks/useApi', () => ({
  useHealth: () => ({ data: { status: 'healthy', version: '0.41.8' } }),
  useUpdateInfo: vi.fn(() => ({ data: null })),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false } }),
  useWantedBatchStatus: () => ({ data: { running: false } }),
  useWantedBatchProbeStatus: () => ({ data: { running: false } }),
}))

vi.mock('@/hooks/useProvidersApi', () => ({
  useProviderHealth: vi.fn(() => ({ data: {} })),
}))

import { StatusBar } from '../StatusBar'

describe('StatusBar', () => {
  beforeEach(() => {
    vi.mocked(useUpdateInfo).mockReturnValue({ data: null })
  })

  it('renders version as plain span when no update available', () => {
    render(<StatusBar />)
    const version = screen.getByTestId('status-bar-version')
    expect(version.tagName).toBe('SPAN')
    expect(version).toHaveTextContent('0.41.8')
  })

  it('renders version as button when update available', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    const version = screen.getByTestId('status-bar-version')
    expect(version.tagName).toBe('BUTTON')
  })

  it('shows update dot when update available', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    expect(screen.getByTestId('status-bar-update-dot')).toBeInTheDocument()
  })

  it('does not show update dot when no update available', () => {
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-update-dot')).not.toBeInTheDocument()
  })

  it('opens popover when version button is clicked', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-update-popover')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('status-bar-version'))
    expect(screen.getByTestId('status-bar-update-popover')).toBeInTheDocument()
    expect(screen.getByTestId('status-bar-update-popover')).toHaveTextContent('0.42.0')
  })

  it('popover contains GitHub link', () => {
    vi.mocked(useUpdateInfo).mockReturnValue({
      data: { available: true, latest: '0.42.0', current: '0.41.8', url: 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0' },
    })
    render(<StatusBar />)
    fireEvent.click(screen.getByTestId('status-bar-version'))
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', 'https://github.com/abrechen2/sublarr/releases/tag/v0.42.0')
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('shows throttled providers warning', () => {
    vi.mocked(useProviderHealth).mockReturnValue({
      data: {
        opensubtitles: { healthy: false, circuit_state: 'open', rate_limited: false },
        addic7ed: { healthy: false, circuit_state: 'closed', rate_limited: true },
        jimaku: { healthy: true, circuit_state: 'closed', rate_limited: false },
      },
    })
    render(<StatusBar />)
    const throttled = screen.getByTestId('status-bar-throttled')
    expect(throttled).toBeInTheDocument()
    expect(throttled).toHaveAttribute('title', 'opensubtitles, addic7ed')
  })

  it('hides throttled warning when no providers are throttled', () => {
    vi.mocked(useProviderHealth).mockReturnValue({
      data: {
        opensubtitles: { healthy: true, circuit_state: 'closed', rate_limited: false },
      },
    })
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-throttled')).not.toBeInTheDocument()
  })
})
