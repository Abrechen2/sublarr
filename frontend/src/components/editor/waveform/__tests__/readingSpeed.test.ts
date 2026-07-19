import { describe, it, expect } from 'vitest'

import {
  classifyReadingSpeed,
  countReadableChars,
  formatCps,
  CPS_OK_MAX,
  CPS_WARN_MAX,
  MIN_DISPLAY_SEC,
} from '../readingSpeed'

describe('countReadableChars', () => {
  it('counts plain text length including spaces', () => {
    expect(countReadableChars('Hallo Welt')).toBe(10)
  })

  it('strips ASS override tags before counting', () => {
    expect(countReadableChars('{\\an8}Top')).toBe(3)
  })

  it('collapses \\N line breaks and whitespace runs to single spaces', () => {
    // "Line one" (8) + " " + "Line two" (8) = 17
    expect(countReadableChars('Line one\\NLine two')).toBe(17)
  })

  it('returns 0 for empty / whitespace-only input', () => {
    expect(countReadableChars('')).toBe(0)
    expect(countReadableChars('   ')).toBe(0)
  })
})

describe('classifyReadingSpeed', () => {
  it('classifies a comfortable line as ok', () => {
    // 10 chars over 2 s = 5 CPS
    const r = classifyReadingSpeed('Hallo Welt', 0, 2)
    expect(r.chars).toBe(10)
    expect(r.durationSec).toBe(2)
    expect(r.cps).toBeCloseTo(5)
    expect(r.level).toBe('ok')
    expect(r.tooShort).toBe(false)
  })

  it('classifies the OK/fast boundary just above CPS_OK_MAX as fast', () => {
    // chars chosen so cps sits just above CPS_OK_MAX (17) over 1 s
    const text = 'x'.repeat(CPS_OK_MAX + 1)
    const r = classifyReadingSpeed(text, 0, 1)
    expect(r.cps).toBeCloseTo(CPS_OK_MAX + 1)
    expect(r.level).toBe('fast')
  })

  it('classifies just above CPS_WARN_MAX as tooFast', () => {
    const text = 'x'.repeat(CPS_WARN_MAX + 1)
    const r = classifyReadingSpeed(text, 0, 1)
    expect(r.cps).toBeCloseTo(CPS_WARN_MAX + 1)
    expect(r.level).toBe('tooFast')
  })

  it('treats exactly CPS_OK_MAX as still ok (strict >)', () => {
    const text = 'x'.repeat(CPS_OK_MAX)
    const r = classifyReadingSpeed(text, 0, 1)
    expect(r.cps).toBeCloseTo(CPS_OK_MAX)
    expect(r.level).toBe('ok')
  })

  it('flags a text cue with zero duration as tooFast with null cps', () => {
    const r = classifyReadingSpeed('text', 5, 5)
    expect(r.durationSec).toBe(0)
    expect(r.cps).toBeNull()
    expect(r.level).toBe('tooFast')
  })

  it('keeps an empty zero-duration cue as ok', () => {
    const r = classifyReadingSpeed('', 5, 5)
    expect(r.cps).toBeNull()
    expect(r.level).toBe('ok')
    expect(r.tooShort).toBe(false)
  })

  it('sets tooShort when a text cue is below MIN_DISPLAY_SEC', () => {
    const r = classifyReadingSpeed('hi', 0, MIN_DISPLAY_SEC - 0.1)
    expect(r.tooShort).toBe(true)
  })

  it('does not set tooShort for an empty short cue', () => {
    const r = classifyReadingSpeed('', 0, MIN_DISPLAY_SEC - 0.1)
    expect(r.tooShort).toBe(false)
  })

  it('honours custom thresholds', () => {
    // 10 chars / 1 s = 10 CPS; with okMax=5 that is fast, with warnMax=8 tooFast
    const r = classifyReadingSpeed('x'.repeat(10), 0, 1, { okMax: 5, warnMax: 8 })
    expect(r.level).toBe('tooFast')
  })

  it('clamps a negative duration to zero', () => {
    const r = classifyReadingSpeed('text', 5, 3)
    expect(r.durationSec).toBe(0)
  })
})

describe('formatCps', () => {
  it('formats a finite rate to one decimal', () => {
    expect(formatCps(23.456)).toBe('23.5')
  })

  it('renders ∞ for null / non-finite', () => {
    expect(formatCps(null)).toBe('∞')
    expect(formatCps(Infinity)).toBe('∞')
  })
})
