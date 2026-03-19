import { describe, it, expect } from 'vitest'
import { reorderProviders } from '../pages/Settings/ProvidersTab'

describe('reorderProviders utility', () => {
  it('moves item from index 0 to index 2', () => {
    const items = ['opensubtitles', 'jimaku', 'subscene', 'subdl']
    expect(reorderProviders(items, 0, 2)).toEqual(['jimaku', 'subscene', 'opensubtitles', 'subdl'])
  })

  it('moves item from index 2 to index 0', () => {
    expect(reorderProviders(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
  })

  it('is a no-op when source equals destination', () => {
    const items = ['a', 'b', 'c']
    expect(reorderProviders(items, 1, 1)).toEqual(items)
  })

  it('returns a new array (immutable)', () => {
    const items = ['a', 'b']
    expect(reorderProviders(items, 0, 1)).not.toBe(items)
  })

  it('handles single-item list', () => {
    expect(reorderProviders(['a'], 0, 0)).toEqual(['a'])
  })
})
