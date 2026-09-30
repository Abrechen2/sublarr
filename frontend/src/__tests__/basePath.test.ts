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

describe('basePathFromDocument', () => {
  // The backend used to hand the prefix over in an inline <script>, which the
  // strict script-src CSP blocks — behind a prefixed proxy the app then called
  // the API and routed at "/". The <base> element it rewrites is not script.
  function docWithBase(href: string | null): Document {
    const doc = document.implementation.createHTMLDocument('shell')
    if (href !== null) {
      const base = doc.createElement('base')
      base.setAttribute('href', href)
      doc.head.appendChild(base)
    }
    return doc
  }

  it('reads the prefix the server wrote into <base>', async () => {
    const { basePathFromDocument } = await import('@/basePath')
    expect(basePathFromDocument(docWithBase('/sublarr/'))).toBe('/sublarr')
    expect(basePathFromDocument(docWithBase('/media/subs/'))).toBe('/media/subs')
  })

  it('means the root for "/" or a missing <base>', async () => {
    const { basePathFromDocument } = await import('@/basePath')
    expect(basePathFromDocument(docWithBase('/'))).toBe('')
    expect(basePathFromDocument(docWithBase(null))).toBe('')
  })

  it('refuses a <base> that is not a path prefix', async () => {
    const { basePathFromDocument } = await import('@/basePath')
    expect(basePathFromDocument(docWithBase('//evil.example.com/'))).toBe('')
  })
})
