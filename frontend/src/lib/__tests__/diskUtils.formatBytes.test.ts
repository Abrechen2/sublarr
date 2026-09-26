import { describe, it, expect } from 'vitest'
import { formatBytes } from '../diskUtils'

describe('formatBytes', () => {
  it('keeps the existing small units', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(79_802_187)).toBe('76.1 MB')
    expect(formatBytes(44_126_969_280)).toBe('41.1 GB')
  })

  it('goes on to TB instead of "1024.0 GB" (the sweep reaches that)', () => {
    expect(formatBytes(1024 ** 4)).toBe('1.0 TB')
    expect(formatBytes(38.5 * 1024 ** 4)).toBe('38.5 TB')
  })

  it('never shows nonsense for a negative or invalid value', () => {
    expect(formatBytes(-5)).toBe('0 B')
    expect(formatBytes(Number.NaN)).toBe('0 B')
  })
})
