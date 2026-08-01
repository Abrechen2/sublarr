import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { SettingsDetailLayout } from '../SettingsDetailLayout'

import enCommon from '../../../i18n/locales/en/common.json'

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
      return lookupKey(enCommon, key) ?? key
    },
  }),
}))

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('SettingsDetailLayout', () => {
  it('renders with data-testid="settings-detail-layout"', () => {
    renderWithRouter(<SettingsDetailLayout title="General">content</SettingsDetailLayout>)
    expect(screen.getByTestId('settings-detail-layout')).toBeInTheDocument()
  })

  it('renders the page title via PageHeader', () => {
    renderWithRouter(<SettingsDetailLayout title="General Settings">content</SettingsDetailLayout>)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('General Settings')
  })

  it('renders subtitle when provided', () => {
    renderWithRouter(
      <SettingsDetailLayout title="General" subtitle="Manage basic settings">
        content
      </SettingsDetailLayout>,
    )
    expect(screen.getByTestId('page-header-subtitle')).toHaveTextContent('Manage basic settings')
  })

  it('does not render subtitle element when omitted', () => {
    renderWithRouter(<SettingsDetailLayout title="General">content</SettingsDetailLayout>)
    expect(screen.queryByTestId('page-header-subtitle')).toBeNull()
  })

  it('renders default breadcrumb with Settings link and current title', () => {
    renderWithRouter(<SettingsDetailLayout title="General">content</SettingsDetailLayout>)
    expect(screen.getByText('Settings')).toBeInTheDocument()
    const settingsLink = screen.getByText('Settings').closest('a')
    expect(settingsLink).toHaveAttribute('href', '/settings')
    expect(screen.getAllByText('General').length).toBeGreaterThanOrEqual(1)
  })

  it('renders custom breadcrumb when provided', () => {
    renderWithRouter(
      <SettingsDetailLayout
        title="Providers"
        breadcrumb={[
          { label: 'Settings', href: '/settings' },
          { label: 'Integrations', href: '/settings/integrations' },
          { label: 'Providers' },
        ]}
      >
        content
      </SettingsDetailLayout>,
    )
    expect(screen.getByText('Integrations')).toBeInTheDocument()
    // 'Providers' appears in both breadcrumb and heading — verify at least one exists
    expect(screen.getAllByText('Providers').length).toBeGreaterThanOrEqual(1)
  })

  it('renders children inside the content area', () => {
    renderWithRouter(
      <SettingsDetailLayout title="General">
        <div data-testid="child-content">Settings content</div>
      </SettingsDetailLayout>,
    )
    const contentArea = screen.getByTestId('settings-detail-content')
    expect(contentArea.contains(screen.getByTestId('child-content'))).toBe(true)
  })

  it('renders action slot when provided', () => {
    renderWithRouter(
      <SettingsDetailLayout
        title="General"
        actions={<button data-testid="save-btn">Save</button>}
      >
        content
      </SettingsDetailLayout>,
    )
    expect(screen.getByTestId('save-btn')).toBeInTheDocument()
  })

  it('constrains width via the shared responsive form tier', () => {
    // The cap used to be a hardcoded inline `maxWidth: 780px`. It is now the
    // shared `max-w-form` tier (780 → 960 → 1100px across breakpoints, see the
    // width scale in index.css), so assert the contract — the class — rather
    // than a single pixel value that is only correct on small viewports.
    renderWithRouter(<SettingsDetailLayout title="General">content</SettingsDetailLayout>)
    const root = screen.getByTestId('settings-detail-layout')
    expect(root).toHaveClass('max-w-form')
    expect(root.style.maxWidth).toBe('')
  })

  it('applies additional className to root element', () => {
    renderWithRouter(
      <SettingsDetailLayout title="General" className="extra-class">
        content
      </SettingsDetailLayout>,
    )
    expect(screen.getByTestId('settings-detail-layout')).toHaveClass('extra-class')
  })
})
