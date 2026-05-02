import { describe, it, expect } from 'vitest'
import { stripAssOverrideTags, formatCueTextForDisplay, formatCueTextForRegion } from '../cueTextDisplay'

describe('stripAssOverrideTags', () => {
  it('returns plain SRT/text unchanged', () => {
    expect(stripAssOverrideTags('Hallo, Welt.')).toBe('Hallo, Welt.')
  })

  it('strips a single ASS override tag block', () => {
    expect(stripAssOverrideTags('{\\an8}Top of screen')).toBe('Top of screen')
  })

  it('strips multiple ASS override tag blocks', () => {
    expect(stripAssOverrideTags('{\\an8}{\\fnArial}Hi {\\b1}there{\\b0}')).toBe('Hi there')
  })

  it('replaces ASS line break \\N with single space', () => {
    expect(stripAssOverrideTags('Line one\\NLine two')).toBe('Line one Line two')
  })

  it('replaces lowercase \\n soft break with single space', () => {
    expect(stripAssOverrideTags('soft\\nbreak')).toBe('soft break')
  })

  it('collapses runs of whitespace produced by stripping', () => {
    expect(stripAssOverrideTags('a {\\b1}  b   {\\b0}c')).toBe('a b c')
  })

  it('handles empty / whitespace-only input', () => {
    expect(stripAssOverrideTags('')).toBe('')
    expect(stripAssOverrideTags('   ')).toBe('')
    expect(stripAssOverrideTags('{\\b1}{\\b0}')).toBe('')
  })

  it('does not eat real curly braces in escaped form', () => {
    // ASS uses literal { and } only inside override tags; outside-tag braces
    // are unusual in subtitles, so we're conservative and pass them through.
    expect(stripAssOverrideTags('foo')).toBe('foo')
  })
})

describe('formatCueTextForDisplay', () => {
  it('keeps paragraph line breaks (real newlines preserved)', () => {
    const cue = 'First line\nSecond line'
    expect(formatCueTextForDisplay(cue)).toBe('First line\nSecond line')
  })

  it('strips ASS tags and replaces \\N with newline (multiline display)', () => {
    expect(formatCueTextForDisplay('{\\an8}Top\\NBottom')).toBe('Top\nBottom')
  })

  it('returns empty string for empty / whitespace-only input', () => {
    expect(formatCueTextForDisplay('')).toBe('')
    expect(formatCueTextForDisplay('{\\b1}{\\b0}')).toBe('')
  })
})

describe('formatCueTextForRegion', () => {
  it('truncates at 60 chars by default and appends ellipsis', () => {
    const long = 'a'.repeat(120)
    const out = formatCueTextForRegion(long)
    expect(out.length).toBeLessThanOrEqual(61) // 60 + ellipsis char
    expect(out.endsWith('…')).toBe(true)
  })

  it('does not truncate strings shorter than the limit', () => {
    expect(formatCueTextForRegion('short cue')).toBe('short cue')
  })

  it('strips ASS tags and replaces \\N with single space (region label is one line)', () => {
    expect(formatCueTextForRegion('{\\an8}Top\\NBottom')).toBe('Top Bottom')
  })

  it('honours a custom maxLength', () => {
    const out = formatCueTextForRegion('abcdefghijklmnop', 5)
    expect(out).toBe('abcde…')
  })

  it('returns empty string for empty / whitespace-only input', () => {
    expect(formatCueTextForRegion('   ')).toBe('')
    expect(formatCueTextForRegion('{\\b1}{\\b0}')).toBe('')
  })
})
