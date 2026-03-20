import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { PageHeader } from '../PageHeader'

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('PageHeader', () => {
  it('renders the title', () => {
    renderWithRouter(<PageHeader title="Library" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Library')
  })

  it('exposes data-testid on the root element', () => {
    renderWithRouter(<PageHeader title="Library" />)
    expect(screen.getByTestId('page-header')).toBeInTheDocument()
  })

  it('renders without subtitle when not provided', () => {
    renderWithRouter(<PageHeader title="Library" />)
    expect(screen.queryByTestId('page-header-subtitle')).toBeNull()
  })

  it('renders the subtitle when provided', () => {
    renderWithRouter(<PageHeader title="Library" subtitle="Manage your media" />)
    expect(screen.getByTestId('page-header-subtitle')).toHaveTextContent('Manage your media')
  })

  it('renders without breadcrumb when not provided', () => {
    renderWithRouter(<PageHeader title="Library" />)
    expect(screen.queryByRole('navigation', { name: 'Breadcrumb' })).toBeNull()
  })

  it('renders breadcrumb items when provided', () => {
    renderWithRouter(
      <PageHeader
        title="Detail"
        breadcrumb={[{ label: 'Home', href: '/' }, { label: 'Library', href: '/library' }, { label: 'Detail' }]}
      />
    )
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument()
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.getByText('Library')).toBeInTheDocument()
  })

  it('renders without action slot when not provided', () => {
    renderWithRouter(<PageHeader title="Library" />)
    expect(screen.queryByTestId('page-header-actions')).toBeNull()
  })

  it('renders action slot content when provided', () => {
    renderWithRouter(
      <PageHeader title="Library" actions={<button data-testid="action-btn">Export</button>} />
    )
    expect(screen.getByTestId('page-header-actions')).toBeInTheDocument()
    expect(screen.getByTestId('action-btn')).toBeInTheDocument()
  })

  it('renders title and actions side by side', () => {
    renderWithRouter(
      <PageHeader title="Library" actions={<button>Export</button>} />
    )
    const header = screen.getByTestId('page-header')
    // actions wrapper must exist inside the header
    const actionsWrapper = screen.getByTestId('page-header-actions')
    expect(header.contains(actionsWrapper)).toBe(true)
  })
})
