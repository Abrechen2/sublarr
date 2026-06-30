/**
 * TranslationSettings.test.tsx — Tests for the Translation settings page.
 *
 * Covers:
 * - Renders the page via SettingsDetailLayout
 * - All 6 sections are present (data-testid attributes)
 * - Sections 4-6 (Context & Quality, Sync Engine, Whisper) use the `advanced`
 *   prop and are collapsed by default
 * - Expanding an advanced section via toggle reveals its content
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TranslationSettings } from '../TranslationSettings'
import enSettings from '../../../i18n/locales/en/settings.json'

// ─── Mocks ───────────────────────────────────────────────────────────────────

function lookupKey(ns: Record<string, unknown>, key: string): string | undefined {
  const parts = key.split('.')
  let v: unknown = ns
  for (const p of parts) {
    if (typeof v !== 'object' || v === null) return undefined
    v = (v as Record<string, unknown>)[p]
  }
  return typeof v === 'string' ? v : undefined
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      return lookupKey(enSettings, key) ?? key.split('.').pop() ?? key
    },
  }),
}))

vi.mock('../TranslationTab', () => ({
  TranslationBackendsTab: () => (
    <div data-testid="translation-backends-tab">TranslationBackendsTab</div>
  ),
  PromptPresetsTab: () => <div data-testid="prompt-presets-tab">PromptPresetsTab</div>,
  GlobalGlossaryPanel: () => <div data-testid="global-glossary-panel">GlobalGlossaryPanel</div>,
  ContextWindowSizeRow: () => (
    <div data-testid="context-window-row">ContextWindowSizeRow</div>
  ),
  TranslationQualitySection: () => (
    <div data-testid="translation-quality">TranslationQualitySection</div>
  ),
  TranslationMemorySection: () => (
    <div data-testid="translation-memory">TranslationMemorySection</div>
  ),
  DefaultSyncEngineRow: () => (
    <div data-testid="default-sync-engine">DefaultSyncEngineRow</div>
  ),
  AutoSyncSection: () => <div data-testid="auto-sync">AutoSyncSection</div>,
  EpisodeContextSection: ({ useEpisodeContext }: { useEpisodeContext?: boolean }) => (
    <div data-testid="section-translation-context">
      <div data-testid="toggle-translation-use-episode-context">
        <button
          role="switch"
          aria-checked={useEpisodeContext ?? false}
          onClick={() => {}}
        />
      </div>
      {useEpisodeContext && (
        <input data-testid="input-translation-context-episodes" type="number" defaultValue={1} />
      )}
      <div data-testid="toggle-translation-series-glossary-auto">
        <button role="switch" aria-checked={false} onClick={() => {}} />
      </div>
    </div>
  ),
}))

const mockDisableMutate = vi.fn()
const mockUpdateConfig = vi.fn()
const mockConfigHolder: { data: Record<string, unknown> } = {
  data: { translation_enabled: true, translation_max_workers: 2 },
}
vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({ data: mockConfigHolder.data, isLoading: false }),
  useUpdateConfig: () => ({ mutate: mockUpdateConfig, isPending: false }),
  useDisableTranslation: () => ({ mutate: mockDisableMutate, isPending: false }),
}))

vi.mock('../WhisperTab', () => ({
  WhisperTab: () => <div data-testid="whisper-tab">WhisperTab</div>,
}))

// ─── Test Helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <BrowserRouter>
      <QueryClientProvider client={makeQueryClient()}>
        <TranslationSettings />
      </QueryClientProvider>
    </BrowserRouter>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('TranslationSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockConfigHolder.data = { translation_enabled: true, translation_max_workers: 2 }
  })

  // ── Layout ────────────────────────────────────────────────────────────────

  it('renders inside SettingsDetailLayout', () => {
    renderPage()
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  // ── Section presence ─────────────────────────────────────────────────────

  it('renders the Translation Backends section', () => {
    renderPage()
    expect(screen.getByTestId('section-translation-backends')).toBeInTheDocument()
  })

  it('renders the Prompt Presets section', () => {
    renderPage()
    expect(screen.getByTestId('section-prompt-presets')).toBeInTheDocument()
  })

  it('renders the Global Glossary section', () => {
    renderPage()
    expect(screen.getByTestId('section-global-glossary')).toBeInTheDocument()
  })

  it('renders the Context & Quality section', () => {
    renderPage()
    expect(screen.getByTestId('section-context-quality')).toBeInTheDocument()
  })

  it('renders the Sync Engine section', () => {
    renderPage()
    expect(screen.getByTestId('section-sync-engine')).toBeInTheDocument()
  })

  it('renders the Whisper section', () => {
    renderPage()
    expect(screen.getByTestId('section-whisper')).toBeInTheDocument()
  })

  // ── Section titles ────────────────────────────────────────────────────────

  it('shows "Translation Backends" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-translation-backends')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Translation Backends')
  })

  it('shows "Prompt Presets" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-prompt-presets')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Prompt Presets')
  })

  it('shows "Global Glossary" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-global-glossary')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Global Glossary')
  })

  it('shows "Context & Quality" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-context-quality')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Context & Quality')
  })

  it('shows "Sync Engine" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-sync-engine')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Sync Engine')
  })

  it('Whisper nav card renders a Configure link', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-whisper')
    expect(wrapper.querySelector('a')).toBeInTheDocument()
  })

  // ── Non-advanced sections do NOT have an advanced toggle ─────────────────

  it('Translation Backends section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-translation-backends')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Prompt Presets section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-prompt-presets')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  it('Global Glossary section does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-global-glossary')
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]'),
    ).toBeNull()
  })

  // ── Advanced sections collapsed by default ────────────────────────────────

  it('Context & Quality advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-context-quality')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Sync Engine advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-sync-engine')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
  })

  it('Whisper nav card does not have an advanced toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-whisper')
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')).toBeNull()
  })

  // ── Expanding advanced sections ───────────────────────────────────────────

  it('Context & Quality expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-context-quality')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  it('Sync Engine expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-sync-engine')
    const toggle = wrapper.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(toggle)
    expect(
      wrapper.querySelector('[data-testid="settings-section-advanced-content"]'),
    ).toBeInTheDocument()
  })

  // ── Summary text for advanced sections ───────────────────────────────────

  it('shows a summary description inside the Context & Quality section', () => {
    renderPage()
    expect(screen.getByTestId('context-quality-summary')).toBeInTheDocument()
  })

  it('shows a summary description inside the Sync Engine section', () => {
    renderPage()
    expect(screen.getByTestId('sync-engine-summary')).toBeInTheDocument()
  })

  // ── All sections exist ────────────────────────────────────────────────────

  it('renders exactly 6 settings sections (Whisper is nav card)', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(6)
  })

  // ── Disable Translation ────────────────────────────────────────────────────

  it('renders Disable Translation button', () => {
    renderPage()
    expect(screen.getByRole('button', { name: /disable translation/i })).toBeInTheDocument()
  })

  it('clicking Disable Translation shows confirmation dialog', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /disable translation/i }))
    expect(screen.getByText(/wirklich deaktivieren/i)).toBeInTheDocument()
  })

  it('clicking Bestätigen calls disableTranslation.mutate', async () => {
    mockDisableMutate.mockClear()
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: /disable translation/i }))
    await user.click(screen.getByRole('button', { name: /bestätigen/i }))
    expect(mockDisableMutate).toHaveBeenCalledOnce()
  })

  // ── Enable (when disabled) ──────────────────────────────────────────────────

  it('shows Enable button and hides Disable zone when translation is disabled', () => {
    mockConfigHolder.data = { translation_enabled: false }
    renderPage()
    expect(screen.getByTestId('enable-translation-btn')).toBeInTheDocument()
    expect(screen.queryByTestId('section-disable-translation')).not.toBeInTheDocument()
  })

  it('clicking Enable calls updateConfig with translation_enabled true', async () => {
    mockConfigHolder.data = { translation_enabled: false }
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByTestId('enable-translation-btn'))
    expect(mockUpdateConfig).toHaveBeenCalledWith({ translation_enabled: 'true' })
  })

  it('hides Enable button and shows Disable zone when translation is enabled', () => {
    renderPage()
    expect(screen.queryByTestId('enable-translation-btn')).not.toBeInTheDocument()
    expect(screen.getByTestId('section-disable-translation')).toBeInTheDocument()
  })
})

// ─── Translation Context section (Step 45) ───────────────────────────────────

describe('Translation Context section', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the Episode Context section wrapper', () => {
    renderPage()
    expect(screen.getByTestId('episode-context-content')).toBeInTheDocument()
  })

  it('toggle-translation-use-episode-context renders unchecked by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('toggle-translation-use-episode-context')
    const btn = wrapper.querySelector('[role="switch"]') as HTMLElement
    expect(btn).toHaveAttribute('aria-checked', 'false')
  })

  it('toggle-translation-series-glossary-auto renders unchecked by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('toggle-translation-series-glossary-auto')
    const btn = wrapper.querySelector('[role="switch"]') as HTMLElement
    expect(btn).toHaveAttribute('aria-checked', 'false')
  })
})
