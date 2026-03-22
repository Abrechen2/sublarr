/**
 * LanguageProfiles.test.tsx — Tests for the Language Profiles wrapper page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { LanguageProfilesPage } from '../LanguageProfiles'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('../Settings/AdvancedTab', () => ({
  LanguageProfilesTab: () => <div data-testid="language-profiles-tab">LanguageProfilesTab</div>,
}))

vi.mock('@/components/settings/SettingsDetailLayout', () => ({
  SettingsDetailLayout: ({
    title,
    subtitle,
    children,
  }: {
    title: string
    subtitle: string
    children: React.ReactNode
  }) => (
    <div data-testid="settings-detail-layout">
      <h1>{title}</h1>
      <p>{subtitle}</p>
      {children}
    </div>
  ),
}))

vi.mock('@/components/shared/PageSkeleton', () => ({
  FormSkeleton: () => <div>Loading...</div>,
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderPage() {
  return render(
    <MemoryRouter>
      <LanguageProfilesPage />
    </MemoryRouter>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('LanguageProfilesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders inside SettingsDetailLayout', () => {
    renderPage()
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders "Language Profiles" as the page title', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Language Profiles')
  })

  it('renders LanguageProfilesTab inside the layout', () => {
    renderPage()
    expect(screen.getByTestId('language-profiles-tab')).toBeInTheDocument()
  })
})
