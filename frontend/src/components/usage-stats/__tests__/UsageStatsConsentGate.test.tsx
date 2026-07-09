import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const consentRef = vi.hoisted(() => ({ value: 'unset' as 'unset' | 'granted' | 'denied' }))
vi.mock('@/hooks/useUsageStatsConsent', () => ({
  useUsageStatsConsent: () => ({ consent: consentRef.value, isLoading: false, setConsent: vi.fn() }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { UsageStatsConsentGate } from '../UsageStatsConsentGate'

describe('UsageStatsConsentGate', () => {
  it('shows the consent card when enabled and consent is unset', () => {
    consentRef.value = 'unset'
    render(<UsageStatsConsentGate enabled />)
    expect(screen.getByTestId('usage-stats-accept')).toBeInTheDocument()
  })

  it('renders nothing when disabled (even if unset)', () => {
    consentRef.value = 'unset'
    const { container } = render(<UsageStatsConsentGate enabled={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing once consent is set', () => {
    consentRef.value = 'granted'
    const { container } = render(<UsageStatsConsentGate enabled />)
    expect(container).toBeEmptyDOMElement()
  })
})
