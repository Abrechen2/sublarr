import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SeasonSummaryBar } from '../SeasonSummaryBar'
import type { EpisodeInfo } from '@/lib/types'

function makeEp(overrides: Partial<EpisodeInfo> = {}): EpisodeInfo {
  return {
    id: 1,
    season: 1,
    episode: 1,
    title: 'Test Episode',
    has_file: true,
    file_path: '/media/show/ep01.mkv',
    subtitles: {},
    audio_languages: [],
    monitored: true,
    ...overrides,
  }
}

describe('SeasonSummaryBar', () => {
  it('renders nothing when no file episodes exist', () => {
    const episodes = [makeEp({ has_file: false })]
    const { container } = render(
      <SeasonSummaryBar season={1} episodes={episodes} targetLanguages={['de']} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('shows ok count when all subtitles present', () => {
    const episodes = [
      makeEp({ id: 1, subtitles: { de: 'ass' } }),
      makeEp({ id: 2, episode: 2, subtitles: { de: 'srt' } }),
    ]
    render(<SeasonSummaryBar season={1} episodes={episodes} targetLanguages={['de']} />)
    expect(screen.getByText('2 OK')).toBeInTheDocument()
  })

  it('shows missing count when subtitles absent', () => {
    const episodes = [
      makeEp({ id: 1, subtitles: {} }),
      makeEp({ id: 2, episode: 2, subtitles: { de: 'ass' } }),
    ]
    render(<SeasonSummaryBar season={1} episodes={episodes} targetLanguages={['de']} />)
    expect(screen.getByText('1 Missing')).toBeInTheDocument()
    expect(screen.getByText('1 OK')).toBeInTheDocument()
  })

  it('shows season label', () => {
    const episodes = [makeEp({ subtitles: { de: 'ass' } })]
    render(<SeasonSummaryBar season={3} episodes={episodes} targetLanguages={['de']} />)
    expect(screen.getByLabelText('Season 3 summary')).toBeInTheDocument()
  })

  it('skips episodes without files when counting missing', () => {
    const episodes = [
      makeEp({ id: 1, has_file: false, subtitles: {} }),
      makeEp({ id: 2, episode: 2, has_file: true, subtitles: { de: 'ass' } }),
    ]
    render(<SeasonSummaryBar season={1} episodes={episodes} targetLanguages={['de']} />)
    // Only 1 file episode, which has a sub — should show 1 ok, no missing
    expect(screen.getByText('1 OK')).toBeInTheDocument()
    expect(screen.queryByText(/Missing/)).not.toBeInTheDocument()
  })

  it('does not show zero-count sections', () => {
    const episodes = [makeEp({ subtitles: { de: 'ass' } })]
    render(<SeasonSummaryBar season={1} episodes={episodes} targetLanguages={['de']} />)
    // Should show "1 ok" but not "0 missing" or "0 ok"
    expect(screen.queryByText('0 OK')).not.toBeInTheDocument()
    expect(screen.queryByText('0 Missing')).not.toBeInTheDocument()
  })
})
