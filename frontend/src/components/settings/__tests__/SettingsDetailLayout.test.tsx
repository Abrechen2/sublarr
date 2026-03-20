import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { SettingsDetailLayout } from '../SettingsDetailLayout'

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
    expect(screen.getByText('Providers')).toBeInTheDocument()
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

  it('applies max-width constraint of 780px', () => {
    renderWithRouter(<SettingsDetailLayout title="General">content</SettingsDetailLayout>)
    const root = screen.getByTestId('settings-detail-layout')
    expect(root).toHaveStyle({ maxWidth: '780px' })
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
