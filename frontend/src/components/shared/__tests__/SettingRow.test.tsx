/**
 * The "advanced" badge on SettingRow is translated (settings:advanced_badge),
 * not a hardcoded German string.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from '@/i18n'
import { SettingRow } from '../SettingRow'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

function renderAdvancedRow() {
  return render(
    <AdvancedSettingsProvider>
      <SettingRow label="Some setting" advanced>
        <input aria-label="value" />
      </SettingRow>
    </AdvancedSettingsProvider>,
  )
}

describe('SettingRow advanced badge', () => {
  beforeEach(() => {
    localStorage.setItem('sublarr_show_advanced', 'true')
  })

  afterEach(async () => {
    localStorage.removeItem('sublarr_show_advanced')
    await i18n.changeLanguage('en')
  })

  it('shows the English label in the English UI', async () => {
    await i18n.changeLanguage('en')
    renderAdvancedRow()
    expect(screen.getByText('Advanced')).toBeInTheDocument()
    expect(screen.queryByText('Erweitert')).not.toBeInTheDocument()
  })

  it('shows the German label in the German UI', async () => {
    await i18n.changeLanguage('de')
    renderAdvancedRow()
    expect(screen.getByText('Erweitert')).toBeInTheDocument()
  })

  it('hides advanced rows when advanced settings are off', () => {
    localStorage.setItem('sublarr_show_advanced', 'false')
    renderAdvancedRow()
    expect(screen.queryByText('Some setting')).not.toBeInTheDocument()
  })
})
