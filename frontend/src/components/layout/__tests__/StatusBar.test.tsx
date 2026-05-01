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
  useProviderHealth: vi.fn(() => ({ data: { providers: [] } })),
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
        providers: [
          {
            name: 'opensubtitles',
            healthy: false,
            enabled: true,
            initialized: true,
            success_rate: 0,
            avg_response_time_ms: 0,
            last_response_time_ms: 0,
            auto_disabled: false,
            disabled_until: '',
            consecutive_failures: 5,
            total_searches: 10,
            circuit_breaker_state: 'open',
            throttled_until: null,
            throttle_reason: null,
          },
          {
            name: 'addic7ed',
            healthy: false,
            enabled: true,
            initialized: true,
            success_rate: 0,
            avg_response_time_ms: 0,
            last_response_time_ms: 0,
            auto_disabled: false,
            disabled_until: '',
            consecutive_failures: 0,
            total_searches: 5,
            circuit_breaker_state: 'closed',
            throttled_until: '2099-01-01T00:00:00Z',
            throttle_reason: 'rate_limited',
          },
          {
            name: 'jimaku',
            healthy: true,
            enabled: true,
            initialized: true,
            success_rate: 1,
            avg_response_time_ms: 100,
            last_response_time_ms: 100,
            auto_disabled: false,
            disabled_until: '',
            consecutive_failures: 0,
            total_searches: 20,
            circuit_breaker_state: 'closed',
            throttled_until: null,
            throttle_reason: null,
          },
        ],
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
        providers: [
          {
            name: 'opensubtitles',
            healthy: true,
            enabled: true,
            initialized: true,
            success_rate: 1,
            avg_response_time_ms: 100,
            last_response_time_ms: 100,
            auto_disabled: false,
            disabled_until: '',
            consecutive_failures: 0,
            total_searches: 30,
            circuit_breaker_state: 'closed',
            throttled_until: null,
            throttle_reason: null,
          },
        ],
      },
    })
    render(<StatusBar />)
    expect(screen.queryByTestId('status-bar-throttled')).not.toBeInTheDocument()
  })

  it('treats auto_disabled providers as throttled', () => {
    vi.mocked(useProviderHealth).mockReturnValue({
      data: {
        providers: [
          {
            name: 'opensubtitles',
            healthy: false,
            enabled: true,
            initialized: true,
            success_rate: 0,
            avg_response_time_ms: 0,
            last_response_time_ms: 0,
            auto_disabled: true,
            disabled_until: '2099-01-01T00:00:00Z',
            consecutive_failures: 10,
            total_searches: 10,
            circuit_breaker_state: 'closed',
            throttled_until: null,
            throttle_reason: null,
          },
        ],
      },
    })
    render(<StatusBar />)
    const throttled = screen.getByTestId('status-bar-throttled')
    expect(throttled).toBeInTheDocument()
    expect(throttled).toHaveAttribute('title', 'opensubtitles')
  })
})
