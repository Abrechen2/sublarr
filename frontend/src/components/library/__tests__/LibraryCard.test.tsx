import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LibraryCard } from '../LibraryCard'
import type { SeriesInfo, MovieInfo } from '@/lib/types'

const baseSeries: SeriesInfo = {
  id: 1,
  title: 'Attack on Titan',
  year: 2013,
  seasons: 4,
  episodes: 87,
  episodes_with_files: 87,
  path: '/media/aot',
  poster: '',
  status: 'ended',
  profile_id: 1,
  profile_name: 'German',
  missing_count: 0,
}

const baseMovie: MovieInfo = {
  id: 2,
  title: 'Spirited Away',
  year: 2001,
  has_file: true,
  path: '/media/spirited',
  poster: '',
  status: 'released',
}

describe('LibraryCard', () => {
  it('renders card with testid', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.getByTestId('library-card')).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(<LibraryCard item={baseSeries} onClick={onClick} />)
    fireEvent.click(screen.getByTestId('library-card'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows series title', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.getByText('Attack on Titan')).toBeInTheDocument()
  })

  it('shows movie title', () => {
    render(<LibraryCard item={baseMovie} onClick={() => {}} />)
    expect(screen.getByText('Spirited Away')).toBeInTheDocument()
  })

  it('shows Tv placeholder when no poster for series', () => {
    const { container } = render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    // no img element rendered
    expect(container.querySelector('img')).toBeNull()
    // Lucide Tv icon should be present (svg)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('renders poster image when provided', () => {
    const item = { ...baseSeries, poster: 'https://example.com/poster.jpg' }
    render(<LibraryCard item={item} onClick={() => {}} />)
    const img = screen.getByRole('img')
    expect(img).toHaveAttribute('src', 'https://example.com/poster.jpg')
    expect(img).toHaveAttribute('alt', 'Attack on Titan')
  })

  it('does NOT show missing badge when missing_count is 0', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.queryByTestId('library-card-missing-badge')).toBeNull()
  })

  it('shows missing badge with count when missing_count > 0', () => {
    const item = { ...baseSeries, missing_count: 5 }
    render(<LibraryCard item={item} onClick={() => {}} />)
    const badge = screen.getByTestId('library-card-missing-badge')
    expect(badge).toHaveTextContent('5')
  })

  it('shows complete icon when series is fully covered', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.getByTestId('library-card-complete-icon')).toBeInTheDocument()
  })

  it('does NOT show complete icon when series has missing subs', () => {
    const item = { ...baseSeries, missing_count: 3 }
    render(<LibraryCard item={item} onClick={() => {}} />)
    expect(screen.queryByTestId('library-card-complete-icon')).toBeNull()
  })

  it('shows meta line for series', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    const meta = screen.getByTestId('library-card-meta')
    expect(meta.textContent).toContain('87')
  })

  it('does NOT show meta line for movies', () => {
    render(<LibraryCard item={baseMovie} onClick={() => {}} />)
    expect(screen.queryByTestId('library-card-meta')).toBeNull()
  })

  it('shows score badge for fully-covered series', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.getByTestId('library-card-score-badge')).toBeInTheDocument()
  })

  it('does NOT show score badge when series has missing subs', () => {
    const item = { ...baseSeries, missing_count: 2 }
    render(<LibraryCard item={item} onClick={() => {}} />)
    expect(screen.queryByTestId('library-card-score-badge')).toBeNull()
  })

  it('shows profile name for series', () => {
    render(<LibraryCard item={baseSeries} onClick={() => {}} />)
    expect(screen.getByText('German')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <LibraryCard item={baseSeries} onClick={() => {}} className="my-custom" />,
    )
    expect(container.firstChild).toHaveClass('my-custom')
  })
})
