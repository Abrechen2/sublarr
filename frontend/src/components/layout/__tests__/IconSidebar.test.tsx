import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

vi.mock('@/hooks/useApi', () => ({
  useHealth: () => ({ data: { status: 'healthy', version: '0.33.0' } }),
  useUpdateInfo: () => ({ data: null }),
}))

vi.mock('@/hooks/useWantedApi', () => ({
  useWantedSummary: () => ({ data: { total: 5 } }),
  useScannerStatus: () => ({ data: { is_scanning: false, is_searching: false } }),
}))

vi.mock('@/components/shared/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Theme</button>,
}))

import { IconSidebar } from '../IconSidebar'

function renderWithRouter(ui: React.ReactElement, { route = '/' } = {}) {
  window.history.pushState({}, 'Test page', route)
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('IconSidebar', () => {
  it('renders the logo image', () => {
    renderWithRouter(<IconSidebar />)
    const logo = screen.getByTestId('sidebar-logo')
    expect(logo).toBeInTheDocument()
    expect(logo.tagName).toBe('IMG')
  })

  it('renders 3 main nav items (Dashboard, Library, Activity)', () => {
    renderWithRouter(<IconSidebar />)
    expect(screen.getByTestId('nav-link-dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('nav-link-library')).toBeInTheDocument()
    expect(screen.getByTestId('nav-link-activity')).toBeInTheDocument()
  })

  it('renders settings nav item', () => {
    renderWithRouter(<IconSidebar />)
    expect(screen.getByTestId('nav-link-settings')).toBeInTheDocument()
  })

  it('renders theme toggle', () => {
    renderWithRouter(<IconSidebar />)
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
  })

  it('highlights the active route with aria-current', () => {
    renderWithRouter(<IconSidebar />, { route: '/library' })
    const libraryLink = screen.getByTestId('nav-link-library')
    expect(libraryLink).toHaveAttribute('aria-current', 'page')
  })

  it('does not highlight inactive routes', () => {
    renderWithRouter(<IconSidebar />, { route: '/' })
    const libraryLink = screen.getByTestId('nav-link-library')
    expect(libraryLink).not.toHaveAttribute('aria-current')
  })

  it('shows badge on Activity when there are wanted items', () => {
    renderWithRouter(<IconSidebar />)
    const badge = screen.getByTestId('activity-badge')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveTextContent('5')
  })

  it('has aria-labels on nav items', () => {
    renderWithRouter(<IconSidebar />)
    expect(screen.getByTestId('nav-link-dashboard')).toHaveAttribute('aria-label')
    expect(screen.getByTestId('nav-link-library')).toHaveAttribute('aria-label')
    expect(screen.getByTestId('nav-link-activity')).toHaveAttribute('aria-label')
    expect(screen.getByTestId('nav-link-settings')).toHaveAttribute('aria-label')
  })

  it('has the collapsed sidebar class by default', () => {
    renderWithRouter(<IconSidebar />)
    const sidebar = screen.getByTestId('icon-sidebar')
    expect(sidebar.className).toMatch(/w-\[48px\]/)
  })

  it('has a separator between main nav and bottom items', () => {
    renderWithRouter(<IconSidebar />)
    const separator = screen.getByTestId('sidebar-separator')
    expect(separator).toBeInTheDocument()
  })

  it('renders version text', () => {
    renderWithRouter(<IconSidebar />)
    expect(screen.getByTestId('sidebar-version')).toHaveTextContent('0.33.0')
  })
})
