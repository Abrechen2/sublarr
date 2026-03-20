import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key.split('.').pop() ?? key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

import { EpisodeGridHeader, episodeGridRowStyle, FormatBadge, EPISODE_GRID_COLUMNS } from '../EpisodeGrid'

describe('EpisodeGridHeader', () => {
  it('renders 6 column labels', () => {
    render(<EpisodeGridHeader />)
    expect(screen.getByText('#')).toBeInTheDocument()
    expect(screen.getByText('Episode')).toBeInTheDocument()
    expect(screen.getByText('Format')).toBeInTheDocument()
    expect(screen.getByText('Provider')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('uses CSS grid with 6 columns', () => {
    const { container } = render(<EpisodeGridHeader />)
    const header = container.firstChild as HTMLElement
    expect(header.style.display).toBe('grid')
    expect(header.style.gridTemplateColumns).toBe('50px 1fr 80px 90px 70px 140px')
  })
})

describe('episodeGridRowStyle', () => {
  it('returns grid style for ok status', () => {
    const style = episodeGridRowStyle({ status: 'ok' })
    expect(style.display).toBe('grid')
    expect(style.gridTemplateColumns).toBe(EPISODE_GRID_COLUMNS)
    expect(style.borderLeft).toContain('transparent')
  })

  it('returns error border for missing status', () => {
    const style = episodeGridRowStyle({ status: 'missing' })
    expect(style.borderLeft).toContain('var(--error)')
  })

  it('returns warning border for low-score status', () => {
    const style = episodeGridRowStyle({ status: 'low-score' })
    expect(style.borderLeft).toContain('var(--warning)')
  })

  it('uses hover bg when expanded', () => {
    const style = episodeGridRowStyle({ status: 'ok', isExpanded: true })
    expect(style.backgroundColor).toBe('var(--bg-surface-hover)')
  })
})

describe('FormatBadge', () => {
  it('renders format label uppercase', () => {
    render(<FormatBadge format="ass" />)
    expect(screen.getByText('ASS')).toBeInTheDocument()
  })

  it('strips embedded_ prefix', () => {
    render(<FormatBadge format="embedded_ass" />)
    expect(screen.getByText('ASS')).toBeInTheDocument()
  })

  it('renders dash for empty format', () => {
    const { container } = render(<FormatBadge format="" />)
    expect(container.textContent).toBe('—')
  })
})
