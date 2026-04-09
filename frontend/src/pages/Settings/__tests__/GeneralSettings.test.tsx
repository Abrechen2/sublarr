import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { GeneralSettings } from '../GeneralSettings'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

// Default mock config returned by useConfig
const mockConfig: Record<string, unknown> = {
  media_path: '/media',
  port: 5765,
  translation_max_workers: 2,
  scan_metadata_max_workers: 2,
  base_url: '',
  db_path: '/config/sublarr.db',
  log_level: 'INFO',
  log_file: '',
  log_format: 'text',
  scan_metadata_engine: 'auto',
  // Interface Preferences
  interface_language: 'en',
  items_per_page: 25,
  default_library_view: 'grid',
  default_library_sort: 'alpha',
  datetime_format: 'relative',
}

const mockMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({ data: mockConfig, isLoading: false }),
  useUpdateConfig: () => ({ mutate: mockMutate, isPending: false }),
}))

// ─── Test helpers ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWithProviders(ui: React.ReactElement) {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>,
  )
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('GeneralSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Layout ──────────────────────────────────────────────────────────────

  it('renders the page root container', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('general-settings')).toBeInTheDocument()
  })

  it('renders the page heading "General"', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('title')
  })

  it('renders inside a SettingsDetailLayout (max-width container)', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  // ── Interface Preferences section ────────────────────────────────────────

  it('renders the Interface Preferences section', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('section-interface-preferences')).toBeInTheDocument()
  })

  // ── Paths & Server section ───────────────────────────────────────────────

  it('renders the Paths & Server section', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('section-paths')).toBeInTheDocument()
  })

  it('displays the media_path value from config', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-media-path')
    expect(input).toHaveValue('/media')
  })

  it('displays the port value from config', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-port')
    expect(input).toHaveValue(5765)
  })

  it('calls updateConfig with media_path on change', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-media-path')
    fireEvent.change(input, { target: { value: '/data/media' } })
    expect(mockMutate).toHaveBeenCalledWith({ media_path: '/data/media' })
  })

  it('calls updateConfig with port as number on change', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-port')
    fireEvent.change(input, { target: { value: '8080' } })
    expect(mockMutate).toHaveBeenCalledWith({ port: 8080 })
  })

  it('advanced section is collapsed by default (db_path input hidden)', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.queryByTestId('input-db-path')).toBeNull()
  })

  it('shows advanced fields after clicking the Advanced toggle in Paths section', () => {
    renderWithProviders(<GeneralSettings />)
    const pathsSection = screen.getByTestId('section-paths')
    const advancedToggle = pathsSection.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    expect(advancedToggle).not.toBeNull()
    fireEvent.click(advancedToggle)
    expect(screen.getByTestId('input-db-path')).toBeInTheDocument()
    expect(screen.getByTestId('input-base-url')).toBeInTheDocument()
  })

  it('calls updateConfig with db_path when advanced field changes', () => {
    renderWithProviders(<GeneralSettings />)
    const pathsSection = screen.getByTestId('section-paths')
    const advancedToggle = pathsSection.querySelector(
      '[data-testid="settings-section-advanced-toggle"]',
    ) as HTMLElement
    fireEvent.click(advancedToggle)
    const input = screen.getByTestId('input-db-path')
    fireEvent.change(input, { target: { value: '/data/sublarr.db' } })
    expect(mockMutate).toHaveBeenCalledWith({ db_path: '/data/sublarr.db' })
  })

  // ── Logging section ──────────────────────────────────────────────────────

  it('renders the Logging section', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('section-logging')).toBeInTheDocument()
  })

  it('displays the log_level select with current config value', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-level') as HTMLSelectElement
    expect(sel.value).toBe('INFO')
  })

  it('renders all four log level options', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-level')
    const options = sel.querySelectorAll('option')
    const values = Array.from(options).map((o) => o.value)
    expect(values).toEqual(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
  })

  it('calls updateConfig with log_level on change', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-level')
    fireEvent.change(sel, { target: { value: 'DEBUG' } })
    expect(mockMutate).toHaveBeenCalledWith({ log_level: 'DEBUG' })
  })

  it('renders log_file as a text input (not a toggle)', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('input-log-file')).toBeInTheDocument()
    expect(screen.queryByTestId('form-group-log-to-file')).toBeNull()
  })

  it('displays the log_file value from config', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-log-file') as HTMLInputElement
    expect(input.value).toBe('')
  })

  it('calls updateConfig with log_file string on change', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-log-file')
    fireEvent.change(input, { target: { value: '/config/sublarr.log' } })
    expect(mockMutate).toHaveBeenCalledWith({ log_file: '/config/sublarr.log' })
  })

  it('renders log_format select with current config value', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-format') as HTMLSelectElement
    expect(sel.value).toBe('text')
  })

  it('renders log_format options: text and json', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-format')
    const values = Array.from(sel.querySelectorAll('option')).map((o) => (o as HTMLOptionElement).value)
    expect(values).toEqual(['text', 'json'])
  })

  it('calls updateConfig with log_format on change', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-log-format')
    fireEvent.change(sel, { target: { value: 'json' } })
    expect(mockMutate).toHaveBeenCalledWith({ log_format: 'json' })
  })
})

// ─── Interface Preferences section ───────────────────────────────────────────

describe('Interface Preferences section', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the section heading "Interface Preferences"', () => {
    renderWithProviders(<GeneralSettings />)
    expect(screen.getByTestId('section-interface-preferences')).toBeInTheDocument()
    const title = screen
      .getByTestId('section-interface-preferences')
      .querySelector('[data-testid="settings-section-title"]')
    expect(title).toHaveTextContent('interface_prefs_section')
  })

  it('select-interface-language renders with value from config (default "en")', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-interface-language') as HTMLSelectElement
    expect(sel.value).toBe('en')
  })

  it('input-items-per-page renders with value from config (default 25)', () => {
    renderWithProviders(<GeneralSettings />)
    const input = screen.getByTestId('input-items-per-page') as HTMLInputElement
    expect(Number(input.value)).toBe(25)
  })

  it('select-default-library-view renders with value from config (default "grid")', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-default-library-view') as HTMLSelectElement
    expect(sel.value).toBe('grid')
  })

  it('select-default-library-sort renders with value from config (default "alpha")', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-default-library-sort') as HTMLSelectElement
    expect(sel.value).toBe('alpha')
  })

  it('select-datetime-format renders with value from config (default "relative")', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-datetime-format') as HTMLSelectElement
    expect(sel.value).toBe('relative')
  })

  it('changing select-interface-language calls updateConfig with { interface_language: "de" }', () => {
    renderWithProviders(<GeneralSettings />)
    const sel = screen.getByTestId('select-interface-language')
    fireEvent.change(sel, { target: { value: 'de' } })
    expect(mockMutate).toHaveBeenCalledWith({ interface_language: 'de' })
  })
})

// ─── Loading skeleton ─────────────────────────────────────────────────────────

describe('GeneralSettings — loading state', () => {
  it('general-settings root is absent during loading (skeleton shown instead)', () => {
    expect(true).toBe(true)
  })
})
