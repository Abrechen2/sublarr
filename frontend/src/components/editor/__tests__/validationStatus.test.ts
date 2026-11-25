import { describe, expect, it } from 'vitest'
import { validationStatus } from '../validationStatus'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key

describe('validationStatus (#27)', () => {
  it('shows a warning, not a plain "valid", when the backend warns', () => {
    const s = validationStatus(
      { valid: true, event_count: 0, style_count: 0, warnings: ['No subtitle events found'] },
      t,
    )
    expect(s.tone).toBe('warn')
    expect(s.label).toBe('validation_no_events')
  })

  it('keeps an unknown backend warning visible as given', () => {
    const s = validationStatus({ valid: true, event_count: 3, warnings: ['Odd style'] }, t)
    expect(s.tone).toBe('warn')
    expect(s.label).toBe('Odd style')
  })

  it('is ok for a valid file without warnings', () => {
    const s = validationStatus({ valid: true, event_count: 3, style_count: 1, warnings: [] }, t)
    expect(s.tone).toBe('ok')
    expect(s.label).toBe('validation_ok:{"events":3,"styles":1}')
  })

  it('is an error for an invalid file', () => {
    const s = validationStatus({ valid: false, error: 'bad header', warnings: [] }, t)
    expect(s.tone).toBe('error')
    expect(s.label).toBe('validation_invalid:{"error":"bad header"}')
  })
})
