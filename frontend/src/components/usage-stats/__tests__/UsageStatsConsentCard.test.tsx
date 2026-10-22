import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const setConsent = vi.fn()
vi.mock('@/hooks/useUsageStatsConsent', () => ({
  useUsageStatsConsent: () => ({ consent: 'unset', isLoading: false, setConsent }),
}))

import i18n from '@/i18n'
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

  it('links the German privacy policy and names the controller (DE)', async () => {
    await i18n.changeLanguage('de')
    render(<UsageStatsConsentCard />)
    expect(screen.getByTestId('usage-stats-privacy-link')).toHaveAttribute(
      'href',
      'https://www.abrechen2.de/sublarr/datenschutz/#nutzungsstatistik',
    )
    expect(screen.getByTestId('usage-stats-controller')).toHaveTextContent(
      'Verantwortlich: Dennis Wittke',
    )
    expect(screen.getByText(/pseudonym/)).toBeInTheDocument()
    expect(screen.queryByText(/anonym/i)).toBeNull()
  })

  it('links the English privacy policy and names the controller (EN)', async () => {
    await i18n.changeLanguage('en')
    render(<UsageStatsConsentCard />)
    expect(screen.getByTestId('usage-stats-privacy-link')).toHaveAttribute(
      'href',
      'https://www.abrechen2.de/en/sublarr/privacy/#usage-statistics',
    )
    expect(screen.getByTestId('usage-stats-controller')).toHaveTextContent(
      'Controller: Dennis Wittke',
    )
    expect(screen.queryByText(/anonym/i)).toBeNull()
  })
})
