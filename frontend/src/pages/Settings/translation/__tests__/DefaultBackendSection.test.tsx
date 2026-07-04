import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

const mutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useBackends: () => ({ data: { backends: [
    { name: 'ollama', display_name: 'Ollama (Local LLM)', configured: false },
    { name: 'deepl', display_name: 'DeepL', configured: true },
  ] } }),
  useConfig: () => ({ data: { translation_default_backend: 'ollama', translation_default_fallback: '' } }),
  useUpdateConfig: () => ({ mutate }),
}))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { DefaultBackendSection } from '../DefaultBackendSection'

// `SettingRow` (used inside DefaultBackendSection) requires AdvancedSettingsContext,
// same as every other SettingRow consumer test (see AnidbTab.test.tsx).
function renderSection() {
  return render(
    <AdvancedSettingsProvider>
      <DefaultBackendSection />
    </AdvancedSettingsProvider>,
  )
}

describe('DefaultBackendSection', () => {
  it('saves the primary backend on change', () => {
    renderSection()
    fireEvent.change(screen.getByTestId('default-backend-primary'), { target: { value: 'deepl' } })
    expect(mutate).toHaveBeenCalledWith({ translation_default_backend: 'deepl' })
  })
  it('saves the fallback on change', () => {
    renderSection()
    fireEvent.change(screen.getByTestId('default-backend-fallback'), { target: { value: 'ollama' } })
    expect(mutate).toHaveBeenCalledWith({ translation_default_fallback: 'ollama' })
  })
})
