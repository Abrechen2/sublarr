import { describe, it, expect } from 'vitest'
import { normLang, deriveSubtitlePath } from '../seriesUtils'

describe('normLang', () => {
  it('maps 3-letter ISO 639-2 to 2-letter ISO 639-1', () => {
    expect(normLang('jpn')).toBe('ja')
    expect(normLang('eng')).toBe('en')
    expect(normLang('ger')).toBe('de')
    expect(normLang('deu')).toBe('de')
  })
  it('returns input unchanged if already 2-letter', () => {
    expect(normLang('en')).toBe('en')
    expect(normLang('de')).toBe('de')
  })
  it('returns input unchanged for unknown codes', () => {
    expect(normLang('xyz')).toBe('xyz')
  })
})

describe('deriveSubtitlePath', () => {
  it('constructs subtitle path from media path + lang + format', () => {
    const result = deriveSubtitlePath('/media/show/ep01.mkv', 'de', 'ass')
    expect(result).toBe('/media/show/ep01.de.ass')
  })
  it('handles srt format', () => {
    const result = deriveSubtitlePath('/media/show/ep01.mkv', 'en', 'srt')
    expect(result).toBe('/media/show/ep01.en.srt')
  })
})
