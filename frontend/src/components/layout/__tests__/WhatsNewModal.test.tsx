import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { versionKey, WHATS_NEW } from '@/content/whatsNew'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

// Mutable consent so a single mocked hook can drive both states. vi.hoisted
// keeps the ref accessible inside the (hoisted) vi.mock factory.
const consentRef = vi.hoisted(() => ({ value: 'granted' as 'unset' | 'granted' | 'denied' }))
vi.mock('@/hooks/useUsageStatsConsent', () => ({
  useUsageStatsConsent: () => ({ consent: consentRef.value, isLoading: false, setConsent: vi.fn() }),
}))

import { WhatsNewModal } from '../WhatsNewModal'

beforeEach(() => {
  consentRef.value = 'granted'
})

describe('versionKey', () => {
  it('normalises a pre-release version to the content key', () => {
    expect(versionKey('1.6.0-beta')).toBe('1.6.0')
    expect(versionKey('v1.6.0')).toBe('1.6.0')
    expect(versionKey('1.6.0')).toBe('1.6.0')
  })
  it('returns null when no content exists for the version', () => {
    expect(versionKey('1.5.0')).toBeNull()
    expect(versionKey(undefined)).toBeNull()
  })
})

describe('WhatsNewModal', () => {
  it('renders a highlight per item for the version', () => {
    render(<WhatsNewModal open version="1.6.0" onDismiss={() => {}} />)
    const items = WHATS_NEW['1.6.0']
    for (const item of items) {
      expect(screen.getByText(item.titleKey)).toBeInTheDocument()
    }
  })

  it('renders nothing when closed or version is null', () => {
    const { container, rerender } = render(
      <WhatsNewModal open={false} version="1.6.0" onDismiss={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
    rerender(<WhatsNewModal open version={null} onDismiss={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the usage-stats consent card only when consent is unset', () => {
    consentRef.value = 'unset'
    render(<WhatsNewModal open version="1.6.0" onDismiss={() => {}} />)
    expect(screen.getByTestId('usage-stats-accept')).toBeInTheDocument()
  })

  it('hides the consent card once a choice was made', () => {
    consentRef.value = 'granted'
    render(<WhatsNewModal open version="1.6.0" onDismiss={() => {}} />)
    expect(screen.queryByTestId('usage-stats-accept')).not.toBeInTheDocument()
  })
})
