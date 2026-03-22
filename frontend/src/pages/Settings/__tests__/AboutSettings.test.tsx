import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AboutSettings } from '../AboutSettings'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/api/client', () => ({
  getHealth: vi.fn().mockResolvedValue({
    status: 'healthy',
    version: '0.33.0-beta',
    services: {},
  }),
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

describe('AboutSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Layout ──────────────────────────────────────────────────────────────

  it('renders inside a SettingsDetailLayout', () => {
    renderWithProviders(<AboutSettings />)
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page heading "About"', () => {
    renderWithProviders(<AboutSettings />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('About')
  })

  it('renders the about-settings root container', () => {
    renderWithProviders(<AboutSettings />)
    expect(screen.getByTestId('about-settings')).toBeInTheDocument()
  })

  // ── Sections ────────────────────────────────────────────────────────────

  it('renders the section-version section', () => {
    renderWithProviders(<AboutSettings />)
    expect(screen.getByTestId('section-version')).toBeInTheDocument()
  })

  it('renders the section-links section', () => {
    renderWithProviders(<AboutSettings />)
    expect(screen.getByTestId('section-links')).toBeInTheDocument()
  })

  // ── GitHub link ─────────────────────────────────────────────────────────

  it('renders the GitHub Star link', () => {
    renderWithProviders(<AboutSettings />)
    const link = screen.getByTestId('link-github')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://github.com/abrechen2/sublarr')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  // ── Donation link ───────────────────────────────────────────────────────

  it('renders the Donate link', () => {
    renderWithProviders(<AboutSettings />)
    const link = screen.getByTestId('link-donate')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  // ── Issues link ─────────────────────────────────────────────────────────

  it('renders the Report Issue link', () => {
    renderWithProviders(<AboutSettings />)
    const link = screen.getByTestId('link-issues')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', 'https://github.com/abrechen2/sublarr/issues')
    expect(link).toHaveAttribute('target', '_blank')
  })
})
