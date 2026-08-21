import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { ProviderLanguageExcludes } from '../ProviderLanguageExcludes'
import { parseLanguageExcludes } from '../languageExcludes'

function renderWithProviders(ui: React.ReactElement) {
  return render(<AdvancedSettingsProvider>{ui}</AdvancedSettingsProvider>)
}

// ─── i18n ─────────────────────────────────────────────────────────────────────
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// ─── API hooks ────────────────────────────────────────────────────────────────
const mockMutate = vi.fn()
let mockConfig: Record<string, unknown> = {}

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({ data: mockConfig, isLoading: false }),
  useSupportedLanguages: () => ({
    data: [
      { code: 'en', name: 'English' },
      { code: 'sr', name: 'Serbian' },
      { code: 'hr', name: 'Croatian' },
    ],
  }),
  useUpdateConfig: () => ({ mutate: mockMutate }),
}))

describe('parseLanguageExcludes', () => {
  it('parses a valid object', () => {
    expect(parseLanguageExcludes('{"opensubtitles": ["sr", "hr"]}')).toEqual({
      opensubtitles: ['sr', 'hr'],
    })
  })

  it('returns empty for invalid JSON, non-objects and empty input', () => {
    expect(parseLanguageExcludes('{oops')).toEqual({})
    expect(parseLanguageExcludes('["sr"]')).toEqual({})
    expect(parseLanguageExcludes('')).toEqual({})
    expect(parseLanguageExcludes(undefined)).toEqual({})
  })

  it('drops non-list entries and empty lists', () => {
    expect(parseLanguageExcludes('{"a": "sr", "b": [], "c": ["sr"]}')).toEqual({ c: ['sr'] })
  })
})

describe('ProviderLanguageExcludes', () => {
  beforeEach(() => {
    mockMutate.mockClear()
    mockConfig = {}
  })

  it('renders the current exclusions as pills', () => {
    mockConfig = { provider_language_excludes_json: '{"opensubtitles": ["sr"]}' }
    renderWithProviders(
      <ProviderLanguageExcludes providerName="opensubtitles" providerLanguages={['en', 'sr']} />,
    )
    expect(screen.getByTestId('provider-language-excludes-opensubtitles')).toBeInTheDocument()
    expect(screen.getByText(/Serbian/)).toBeInTheDocument()
  })

  it('adding a language saves the merged JSON setting', () => {
    mockConfig = { provider_language_excludes_json: '{"titlovi": ["en"]}' }
    renderWithProviders(
      <ProviderLanguageExcludes providerName="opensubtitles" providerLanguages={['en', 'sr']} />,
    )
    const select = screen
      .getByTestId('provider-language-excludes-opensubtitles')
      .querySelector('select')
    expect(select).not.toBeNull()
    fireEvent.change(select as HTMLSelectElement, { target: { value: 'sr' } })

    expect(mockMutate).toHaveBeenCalledTimes(1)
    const payload = mockMutate.mock.calls[0][0] as { provider_language_excludes_json: string }
    expect(JSON.parse(payload.provider_language_excludes_json)).toEqual({
      titlovi: ['en'],
      opensubtitles: ['sr'],
    })
  })

  it('removing the last language drops the provider from the map', () => {
    mockConfig = { provider_language_excludes_json: '{"opensubtitles": ["sr"]}' }
    renderWithProviders(
      <ProviderLanguageExcludes providerName="opensubtitles" providerLanguages={['en', 'sr']} />,
    )
    const removeButton = screen
      .getByTestId('provider-language-excludes-opensubtitles')
      .querySelector('button')
    expect(removeButton).not.toBeNull()
    fireEvent.click(removeButton as HTMLButtonElement)

    expect(mockMutate).toHaveBeenCalledTimes(1)
    expect(mockMutate.mock.calls[0][0]).toEqual({ provider_language_excludes_json: '' })
  })
})
