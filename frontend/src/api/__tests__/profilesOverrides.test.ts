import { describe, it, expect } from 'vitest'
import { ResolvedSettingsSchema, ScopesTreeSchema } from '../profilesOverrides'

describe('profilesOverrides schemas', () => {
  it('parses a valid scopes tree', () => {
    const data = {
      profiles: [{ id: 1, name: 'Anime DE', is_default: true, series: [], movies: [] }],
      unassigned_series: [],
      unassigned_movies: [],
    }
    const parsed = ScopesTreeSchema.parse(data)
    expect(parsed.profiles).toHaveLength(1)
  })

  it('rejects an invalid profile entry', () => {
    const data = { profiles: [{ id: 'not-a-number' }], unassigned_series: [], unassigned_movies: [] }
    expect(() => ScopesTreeSchema.parse(data)).toThrow()
  })

  it('parses a resolved settings response', () => {
    const data = {
      scope: { type: 'series' as const, id: 1, name: 'Frieren' },
      settings: {
        cleanup_foreign_tracks: {
          effective: true, source: 'series' as const,
          chain: [{ scope: 'series' as const, value: true, label: 'This series' }],
        },
      },
    }
    const parsed = ResolvedSettingsSchema.parse(data)
    expect(parsed.scope.type).toBe('series')
  })
})
