import { describe, it, expect } from 'vitest'
import { formatVersion } from '../version'

describe('formatVersion', () => {
  it('keeps a single leading v for a tag that already has one', () => {
    expect(formatVersion('v1.2.0')).toBe('v1.2.0')
  })
  it('adds a leading v when missing', () => {
    expect(formatVersion('1.2.0')).toBe('v1.2.0')
  })
  it('collapses an accidental double v', () => {
    expect(formatVersion('vv1.2.0')).toBe('v1.2.0')
  })
  it('returns empty string for null/undefined/empty', () => {
    expect(formatVersion(null)).toBe('')
    expect(formatVersion(undefined)).toBe('')
    expect(formatVersion('')).toBe('')
  })
})
