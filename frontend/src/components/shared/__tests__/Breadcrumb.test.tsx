import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { Breadcrumb } from '../Breadcrumb'

function renderWithRouter(ui: React.ReactElement) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('Breadcrumb', () => {
  it('renders all segments', () => {
    renderWithRouter(
      <Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Library', href: '/library' }, { label: 'Detail' }]} />
    )
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.getByText('Library')).toBeInTheDocument()
    expect(screen.getByText('Detail')).toBeInTheDocument()
  })

  it('renders separator icons between segments', () => {
    const { container } = renderWithRouter(
      <Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Library', href: '/library' }, { label: 'Detail' }]} />
    )
    const separators = container.querySelectorAll('svg')
    expect(separators.length).toBe(2)
  })

  it('renders last item as plain text, not a link', () => {
    renderWithRouter(
      <Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Current' }]} />
    )
    const current = screen.getByText('Current')
    expect(current.tagName).toBe('SPAN')
    expect(current.closest('a')).toBeNull()
  })

  it('renders items with href as links', () => {
    renderWithRouter(
      <Breadcrumb items={[{ label: 'Home', href: '/' }, { label: 'Current' }]} />
    )
    const link = screen.getByText('Home')
    expect(link.closest('a')).toHaveAttribute('href', '/')
  })
})
