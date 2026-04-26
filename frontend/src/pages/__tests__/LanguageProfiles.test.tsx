/**
 * LanguageProfiles.test.tsx — Tests for the Language Profiles wrapper page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { LanguageProfilesPage } from '../LanguageProfiles'

// ─── Mocks ───────────────────────────────────────────────────────────────────

import enSettings from '../../i18n/locales/en/settings.json'
import enCommon from '../../i18n/locales/en/common.json'

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
  useTranslation: (ns?: string) => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      const dict = ns === 'settings' ? enSettings : enCommon
      return lookupKey(dict, key) ?? key
    },
  }),
}))

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
