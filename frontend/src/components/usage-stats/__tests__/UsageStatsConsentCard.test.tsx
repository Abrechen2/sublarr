import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const setConsent = vi.fn()
vi.mock('@/hooks/useUsageStatsConsent', () => ({
  useUsageStatsConsent: () => ({ consent: 'unset', isLoading: false, setConsent }),
}))

import { UsageStatsConsentCard } from '../UsageStatsConsentCard'

describe('UsageStatsConsentCard', () => {
  it('calls setConsent("granted") and onChoice on accept', () => {
    const onChoice = vi.fn()
    render(<UsageStatsConsentCard onChoice={onChoice} />)
    fireEvent.click(screen.getByTestId('usage-stats-accept'))
    expect(setConsent).toHaveBeenCalledWith('granted')
    expect(onChoice).toHaveBeenCalledWith('granted')
  })

  it('calls setConsent("denied") on decline', () => {
    render(<UsageStatsConsentCard />)
    fireEvent.click(screen.getByTestId('usage-stats-decline'))
    expect(setConsent).toHaveBeenCalledWith('denied')
  })
})
