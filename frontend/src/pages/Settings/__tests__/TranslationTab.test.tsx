/**
 * TranslationTab.test.tsx — Tests for sub-components in TranslationTab.
 *
 * Covers:
 * - TranslationBackendsTab: request_timeout and backoff_base global fields
 * - TranslationQualitySection: temperature and batch_size fields
 * - GlobalGlossaryPanel: glossary_max_terms field (already implemented)
 * - AutoSyncSection: presence and SettingRow pattern (already implemented)
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  TranslationBackendsTab,
  TranslationQualitySection,
  GlobalGlossaryPanel,
  AutoSyncSection,
} from '../TranslationTab'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}))

// Default: showAdvanced true so advanced SettingRow fields are visible in tests
vi.mock('@/contexts/AdvancedSettingsContext', () => ({
  useAdvancedSettings: () => ({ showAdvanced: true, toggleAdvanced: vi.fn() }),
  AdvancedSettingsProvider: ({ children }: { children: React.ReactNode }) => children,
}))

const mockMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useBackends: () => ({
    data: { backends: [] },
    isLoading: false,
  }),
  useBackendStats: () => ({ data: { stats: [] } }),
  useTestBackend: () => ({ mutate: vi.fn() }),
  useSaveBackendConfig: () => ({ mutate: vi.fn(), isPending: false }),
  useBackendConfig: () => ({ data: {} }),
  useBackendTemplates: () => ({ data: { templates: [] } }),
  usePromptPresets: () => ({ data: { presets: [] }, isLoading: false }),
  useCreatePromptPreset: () => ({ mutate: vi.fn() }),
  useUpdatePromptPreset: () => ({ mutate: vi.fn() }),
  useDeletePromptPreset: () => ({ mutate: vi.fn() }),
  useGlobalGlossaryEntries: () => ({ data: { entries: [] }, isLoading: false }),
  useCreateGlossaryEntry: () => ({ mutate: vi.fn() }),
  useUpdateGlossaryEntry: () => ({ mutate: vi.fn() }),
  useDeleteGlossaryEntry: () => ({ mutate: vi.fn() }),
  useContextWindowSize: () => ({ value: 3, save: vi.fn(), isPending: false }),
  useConfig: () => ({
    data: {
      request_timeout: '90',
      backoff_base: '5',
      temperature: '0.3',
      batch_size: '15',
      translation_quality_enabled: 'true',
      translation_quality_threshold: '50',
      translation_quality_max_retries: '2',
      glossary_enabled: 'true',
      glossary_max_terms: '100',
      auto_sync_after_download: 'false',
      auto_sync_engine: 'ffsubsync',
    },
  }),
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
  useTranslationMemoryStats: () => ({ data: undefined }),
  useClearTranslationMemoryCache: () => ({ mutate: vi.fn() }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Test helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderComponent(ui: React.ReactElement) {
  return render(
    <BrowserRouter>
      <QueryClientProvider client={makeQueryClient()}>{ui}</QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── TranslationBackendsTab — global LLM fields ───────────────────────────────

describe('TranslationBackendsTab — global LLM settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a request_timeout number input', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-request_timeout')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('request_timeout input shows the configured value', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-request_timeout')
    expect((input as HTMLInputElement).value).toBe('90')
  })

  it('request_timeout input calls updateConfig on blur with the new value', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-request_timeout') as HTMLInputElement
    fireEvent.change(input, { target: { value: '120' } })
    fireEvent.blur(input)
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ request_timeout: '120' }),
      expect.anything(),
    )
  })

  it('renders a backoff_base number input', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-backoff_base')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('backoff_base input shows the configured value', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-backoff_base')
    expect((input as HTMLInputElement).value).toBe('5')
  })

  it('backoff_base input calls updateConfig on blur with the new value', () => {
    renderComponent(<TranslationBackendsTab />)
    const input = screen.getByTestId('input-backoff_base') as HTMLInputElement
    fireEvent.change(input, { target: { value: '10' } })
    fireEvent.blur(input)
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ backoff_base: '10' }),
      expect.anything(),
    )
  })
})

// ─── TranslationQualitySection — temperature + batch_size ─────────────────────

describe('TranslationQualitySection — temperature and batch_size fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a temperature number input', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-temperature')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('temperature input shows the configured value', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-temperature')
    expect((input as HTMLInputElement).value).toBe('0.3')
  })

  it('temperature input calls updateConfig on blur with the new value', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-temperature') as HTMLInputElement
    fireEvent.change(input, { target: { value: '0.5' } })
    fireEvent.blur(input)
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ temperature: '0.5' }),
      expect.anything(),
    )
  })

  it('renders a batch_size number input', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-batch_size')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('batch_size input shows the configured value', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-batch_size')
    expect((input as HTMLInputElement).value).toBe('15')
  })

  it('batch_size input calls updateConfig on blur with the new value', () => {
    renderComponent(<TranslationQualitySection />)
    const input = screen.getByTestId('input-batch_size') as HTMLInputElement
    fireEvent.change(input, { target: { value: '20' } })
    fireEvent.blur(input)
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ batch_size: '20' }),
      expect.anything(),
    )
  })
})

// ─── GlobalGlossaryPanel — glossary_max_terms (already present) ────────────────

describe('GlobalGlossaryPanel — glossary_max_terms', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a glossary_max_terms number input', () => {
    renderComponent(<GlobalGlossaryPanel />)
    const input = screen.getByTestId('input-glossary_max_terms')
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
  })

  it('glossary_max_terms shows the configured value', () => {
    renderComponent(<GlobalGlossaryPanel />)
    const input = screen.getByTestId('input-glossary_max_terms')
    expect((input as HTMLInputElement).value).toBe('100')
  })

  it('glossary_max_terms calls updateConfig on blur with the new value', () => {
    renderComponent(<GlobalGlossaryPanel />)
    const input = screen.getByTestId('input-glossary_max_terms') as HTMLInputElement
    fireEvent.change(input, { target: { value: '50' } })
    fireEvent.blur(input)
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ glossary_max_terms: '50' }),
      expect.anything(),
    )
  })
})

// ─── AutoSyncSection — structure (already implemented) ────────────────────────

describe('AutoSyncSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the auto-sync toggle', () => {
    renderComponent(<AutoSyncSection />)
    expect(screen.getByRole('switch')).toBeInTheDocument()
  })

  it('auto-sync toggle is unchecked when config says false', () => {
    renderComponent(<AutoSyncSection />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })
})
