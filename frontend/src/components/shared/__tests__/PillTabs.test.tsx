import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PillTabs } from '../PillTabs'

const tabs = [
  { id: 'all', label: 'All' },
  { id: 'anime', label: 'Anime' },
  { id: 'movies', label: 'Movies' },
]

describe('PillTabs', () => {
  it('renders all tabs', () => {
    render(<PillTabs tabs={tabs} activeTab="all" onChange={vi.fn()} />)
    expect(screen.getByText('All')).toBeInTheDocument()
    expect(screen.getByText('Anime')).toBeInTheDocument()
    expect(screen.getByText('Movies')).toBeInTheDocument()
  })

  it('highlights the active tab', () => {
    render(<PillTabs tabs={tabs} activeTab="anime" onChange={vi.fn()} />)
    const animeButton = screen.getByText('Anime').closest('button')!
    expect(animeButton.className).toContain('bg-[var(--bg-elevated)]')
    const allButton = screen.getByText('All').closest('button')!
    expect(allButton.className).not.toContain('bg-[var(--bg-elevated)]')
  })

  it('calls onChange when a tab is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<PillTabs tabs={tabs} activeTab="all" onChange={onChange} />)
    await user.click(screen.getByText('Movies'))
    expect(onChange).toHaveBeenCalledWith('movies')
  })

  it('shows count badge when count is provided', () => {
    const tabsWithCount = [
      { id: 'all', label: 'All', count: 42 },
      { id: 'anime', label: 'Anime' },
    ]
    render(<PillTabs tabs={tabsWithCount} activeTab="all" onChange={vi.fn()} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })
})
