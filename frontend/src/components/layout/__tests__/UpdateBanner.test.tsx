import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useUpdateInfo } from '@/hooks/useApi'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { version?: string }) =>
      opts?.version ? `${key}:${opts.version}` : key,
  }),
}))

vi.mock('@/hooks/useApi', () => ({ useUpdateInfo: vi.fn() }))

import { UpdateBanner } from '../UpdateBanner'

const KEY = 'sublarr.update-banner.dismissed'
const updateData = (over: Record<string, unknown> = {}) => ({
  data: { available: true, latest: 'v1.2.0', current: '1.1.0', url: 'https://gh/release', ...over },
})

describe('UpdateBanner', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.mocked(useUpdateInfo).mockReturnValue(updateData() as never)
  })

  it('renders nothing when no update is available', () => {
    vi.mocked(useUpdateInfo).mockReturnValue(
      { data: { available: false, latest: null, current: '1.2.0', url: null } } as never,
    )
    const { container } = render(<UpdateBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when the url is missing', () => {
    vi.mocked(useUpdateInfo).mockReturnValue(updateData({ url: null }) as never)
    const { container } = render(<UpdateBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the bar with a single-v version when available', () => {
    render(<UpdateBanner />)
    expect(screen.getByTestId('update-banner')).toBeInTheDocument()
    expect(screen.getByText('update.banner.message:v1.2.0')).toBeInTheDocument()
    expect(screen.queryByText(/vv1\.2\.0/)).toBeNull()
  })

  it('is hidden when the dismissed version equals latest', () => {
    window.localStorage.setItem(KEY, 'v1.2.0')
    const { container } = render(<UpdateBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('re-shows when latest is newer than the dismissed version', () => {
    window.localStorage.setItem(KEY, 'v1.2.0')
    vi.mocked(useUpdateInfo).mockReturnValue(updateData({ latest: 'v1.3.0' }) as never)
    render(<UpdateBanner />)
    expect(screen.getByTestId('update-banner')).toBeInTheDocument()
  })

  it('dismiss button persists to localStorage and hides the bar', () => {
    render(<UpdateBanner />)
    fireEvent.click(screen.getByTestId('update-banner-dismiss'))
    expect(window.localStorage.getItem(KEY)).toBe('v1.2.0')
    expect(screen.queryByTestId('update-banner')).toBeNull()
  })
})
