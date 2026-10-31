import { describe, it, expect } from 'vitest'
import { serializeEnabledProviders } from '../ProvidersCollectionView'

// Audit #61 A11: '' means "every non-opt-in provider" on the backend.
const PROVIDERS = [{ name: 'a' }, { name: 'b' }, { name: 'hub_x', opt_in: true }]

describe('serializeEnabledProviders', () => {
  it('writes none when the last provider is switched off', () => {
    expect(serializeEnabledProviders(new Set(), PROVIDERS)).toBe('none')
  })

  it('writes the default marker only for exactly the default set', () => {
    expect(serializeEnabledProviders(new Set(['a', 'b']), PROVIDERS)).toBe('')
  })

  it('names an opt-in provider explicitly, even when everything is on', () => {
    expect(serializeEnabledProviders(new Set(['a', 'b', 'hub_x']), PROVIDERS)).toBe('a,b,hub_x')
  })

  it('names a partial selection', () => {
    expect(serializeEnabledProviders(new Set(['b']), PROVIDERS)).toBe('b')
  })
})
