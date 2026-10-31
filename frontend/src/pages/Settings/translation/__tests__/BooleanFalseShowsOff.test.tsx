import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// Audit #61 A09: GET /config returns real booleans; the sections compared
// against the string 'false', so a switched-off feature still showed "on".
vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      translation_quality_enabled: false,
      translation_quality_threshold: 50,
      translation_quality_max_retries: 2,
      translation_memory_enabled: false,
    },
  }),
  useUpdateConfig: () => ({ mutate: vi.fn() }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { TranslationQualitySection } from '../TranslationQualitySection'

describe('a boolean false from the API', () => {
  it('shows the quality check as off', () => {
    render(
      <AdvancedSettingsProvider>
        <TranslationQualitySection />
      </AdvancedSettingsProvider>,
    )
    const toggle = screen.getAllByRole('switch')[0]
    expect(toggle).toHaveAttribute('aria-checked', 'false')
  })
})
