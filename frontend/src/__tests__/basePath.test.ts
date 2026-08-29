import { describe, it, expect } from 'vitest'
import { normalizeBasePath } from '@/basePath'

describe('normalizeBasePath', () => {
  it('treats an empty value and the root as "served at the root"', () => {
    expect(normalizeBasePath('')).toBe('')
    expect(normalizeBasePath('   ')).toBe('')
    expect(normalizeBasePath('/')).toBe('')
    expect(normalizeBasePath(undefined)).toBe('')
    expect(normalizeBasePath(null)).toBe('')
  })

  it('accepts the shapes a user actually types', () => {
    expect(normalizeBasePath('sublarr')).toBe('/sublarr')
    expect(normalizeBasePath('/sublarr')).toBe('/sublarr')
    expect(normalizeBasePath('/sublarr/')).toBe('/sublarr')
    expect(normalizeBasePath('  /sublarr//  ')).toBe('/sublarr')
  })

  it('keeps nested prefixes intact', () => {
    expect(normalizeBasePath('/media/subs/')).toBe('/media/subs')
  })
})

describe('normalizeBasePath — values that are not a prefix', () => {
  it.each([
    '/x" onload="alert(1)',
    '/x<script>',
    'javascript:alert(1)',
    '//evil.example.com',
    '/a b',
  ])('refuses %s', (bad) => {
    expect(normalizeBasePath(bad)).toBe('')
  })
})
