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
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TranslationSettings } from '../TranslationSettings'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
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

  it('shows "Whisper (Speech-to-Text)" section title', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-whisper')
    const title = wrapper.querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('Whisper')
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

  it('Whisper advanced content is collapsed by default', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-whisper')
    const toggle = wrapper.querySelector('[data-testid="settings-section-advanced-toggle"]')
    expect(toggle).toBeInTheDocument()
    expect(wrapper.querySelector('[data-testid="settings-section-advanced-content"]')).toBeNull()
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

  it('Whisper expands and shows content after clicking toggle', () => {
    renderPage()
    const wrapper = screen.getByTestId('section-whisper')
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

  it('shows a summary description inside the Whisper section', () => {
    renderPage()
    expect(screen.getByTestId('whisper-summary')).toBeInTheDocument()
  })

  // ── All 6 sections exist ──────────────────────────────────────────────────

  it('renders exactly 6 settings sections', () => {
    renderPage()
    const sections = screen.getAllByTestId('settings-section')
    expect(sections).toHaveLength(6)
  })
})
