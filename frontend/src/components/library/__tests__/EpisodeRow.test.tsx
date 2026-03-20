import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { EpisodeRow, getRowStatus, FormatBadge } from '../EpisodeRow'
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

describe('getRowStatus', () => {
  it('returns no-file for episodes without a file', () => {
    expect(getRowStatus(makeEp({ has_file: false }), ['de'])).toBe('no-file')
  })

  it('returns ok when all target languages have subtitles', () => {
    const ep = makeEp({ subtitles: { de: 'ass', en: 'srt' } })
    expect(getRowStatus(ep, ['de', 'en'])).toBe('ok')
  })

  it('returns missing when any target language lacks a subtitle', () => {
    const ep = makeEp({ subtitles: { de: 'ass' } })
    expect(getRowStatus(ep, ['de', 'en'])).toBe('missing')
  })

  it('returns missing when subtitle value is empty string', () => {
    const ep = makeEp({ subtitles: { de: '' } })
    expect(getRowStatus(ep, ['de'])).toBe('missing')
  })

  it('returns ok when no target languages configured', () => {
    expect(getRowStatus(makeEp({ subtitles: {} }), [])).toBe('ok')
  })
})

describe('EpisodeRow', () => {
  it('renders children', () => {
    const ep = makeEp({ subtitles: { de: 'ass' } })
    const { getByText } = render(
      <EpisodeRow ep={ep} targetLanguages={['de']}>
        <span>child content</span>
      </EpisodeRow>
    )
    expect(getByText('child content')).toBeInTheDocument()
  })

  it('applies data-status attribute for ok status', () => {
    const ep = makeEp({ subtitles: { de: 'ass' } })
    const { container } = render(
      <EpisodeRow ep={ep} targetLanguages={['de']}>
        <span>content</span>
      </EpisodeRow>
    )
    expect(container.firstChild).toHaveAttribute('data-status', 'ok')
  })

  it('applies data-status attribute for missing status', () => {
    const ep = makeEp({ subtitles: {} })
    const { container } = render(
      <EpisodeRow ep={ep} targetLanguages={['de']}>
        <span>content</span>
      </EpisodeRow>
    )
    expect(container.firstChild).toHaveAttribute('data-status', 'missing')
  })

  it('applies data-status attribute for no-file status', () => {
    const ep = makeEp({ has_file: false })
    const { container } = render(
      <EpisodeRow ep={ep} targetLanguages={['de']}>
        <span>content</span>
      </EpisodeRow>
    )
    expect(container.firstChild).toHaveAttribute('data-status', 'no-file')
  })

  it('has a left border style', () => {
    const ep = makeEp({ subtitles: { de: 'ass' } })
    const { container } = render(
      <EpisodeRow ep={ep} targetLanguages={['de']}>
        <span>content</span>
      </EpisodeRow>
    )
    const el = container.firstChild as HTMLElement
    expect(el.style.borderLeft).toContain('2px solid')
  })
})

describe('FormatBadge', () => {
  it('renders ass format', () => {
    const { getByText } = render(<FormatBadge format="ass" />)
    expect(getByText('ass')).toBeInTheDocument()
  })

  it('renders embedded_ass with ⊕ suffix', () => {
    const { getByText } = render(<FormatBadge format="embedded_ass" />)
    expect(getByText('ass⊕')).toBeInTheDocument()
  })

  it('renders srt format', () => {
    const { getByText } = render(<FormatBadge format="srt" />)
    expect(getByText('srt')).toBeInTheDocument()
  })

  it('renders embedded_srt with ⊕ suffix', () => {
    const { getByText } = render(<FormatBadge format="embedded_srt" />)
    expect(getByText('srt⊕')).toBeInTheDocument()
  })
})
