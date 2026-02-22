import { describe, it, expect } from 'vitest'
import { formatDuration, formatRelativeTime, truncatePath, cn } from '@/lib/utils'

describe('formatDuration', () => {
  it('formats seconds', () => {
    expect(formatDuration(30)).toBe('30s')
  })

  it('formats minutes', () => {
    expect(formatDuration(125)).toBe('2m 5s')
  })

  it('formats hours', () => {
    expect(formatDuration(3665)).toBe('1h 1m')
  })
})

describe('formatRelativeTime', () => {
  it('formats recent time', () => {
    const now = new Date()
    const recent = new Date(now.getTime() - 30 * 1000)
    expect(formatRelativeTime(recent.toISOString())).toBe('just now')
  })

  it('formats minutes ago', () => {
    const now = new Date()
    const minutesAgo = new Date(now.getTime() - 5 * 60 * 1000)
    expect(formatRelativeTime(minutesAgo.toISOString())).toContain('m ago')
  })
})

describe('truncatePath', () => {
  it('truncates long paths', () => {
    const longPath = '/very/long/path/to/file.mkv'
    const truncated = truncatePath(longPath, 20)
    expect(truncated.length).toBeLessThanOrEqual(23) // ... + 20 chars
  })

  it('keeps short paths unchanged', () => {
    const shortPath = '/file.mkv'
    expect(truncatePath(shortPath, 60)).toBe(shortPath)
  })
})

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('handles conditional classes', () => {
    expect(cn('foo', (false as boolean) && 'bar', 'baz')).toBe('foo baz')
  })
})
