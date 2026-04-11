import { describe, it, expect } from 'vitest'

// This import will fail until groupByFilePath is exported from Wanted.tsx in Task 6.
// That's intentional — TDD red phase.
import { groupByFilePath } from '@/pages/Wanted'
import type { WantedItem } from '@/types/wanted'

function makeItem(overrides: Partial<WantedItem>): WantedItem {
  return {
    id: 1,
    item_type: 'episode',
    sonarr_series_id: null,
    sonarr_episode_id: null,
    radarr_movie_id: null,
    title: 'Test',
    season_episode: 'S01E01',
    file_path: '/media/test.mkv',
    existing_sub: '',
    embedded_languages: [],
    missing_languages: [],
    target_language: 'de',
    status: 'wanted',
    last_search_at: '',
    search_count: 0,
    error: '',
    retry_after: null,
    added_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    upgrade_candidate: 0,
    current_score: 0,
    subtitle_type: 'full',
    ...overrides,
  }
}

describe('groupByFilePath', () => {
  it('groups two items with the same file_path into one group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'en' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].languages).toHaveLength(2)
  })

  it('keeps items with different file_paths as separate groups', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/b.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(2)
  })

  it('sorts languages alphabetically within each group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'en' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].languages[0].target_language).toBe('de')
    expect(groups[0].languages[1].target_language).toBe('en')
  })

  it('preserves group order by first occurrence (server sort order)', () => {
    const items = [
      makeItem({ id: 1, file_path: '/z.mkv', target_language: 'de' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].key).toBe('/z.mkv')
    expect(groups[1].key).toBe('/a.mkv')
  })

  it('copies group metadata from the first item', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', title: 'Anime S01E01', season_episode: 'S01E01', item_type: 'episode' }),
      makeItem({ id: 2, file_path: '/a.mkv', title: 'Anime S01E01', season_episode: 'S01E01', item_type: 'episode' }),
    ]
    const [group] = groupByFilePath(items)
    expect(group.title).toBe('Anime S01E01')
    expect(group.season_episode).toBe('S01E01')
    expect(group.item_type).toBe('episode')
  })

  it('handles empty input', () => {
    expect(groupByFilePath([])).toEqual([])
  })

  it('handles single item (single language profile)', () => {
    const items = [makeItem({ id: 1, file_path: '/a.mkv', target_language: 'de' })]
    const groups = groupByFilePath(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].languages).toHaveLength(1)
  })

  it('handles three languages in one group', () => {
    const items = [
      makeItem({ id: 1, file_path: '/a.mkv', target_language: 'ja' }),
      makeItem({ id: 2, file_path: '/a.mkv', target_language: 'de' }),
      makeItem({ id: 3, file_path: '/a.mkv', target_language: 'en' }),
    ]
    const groups = groupByFilePath(items)
    expect(groups[0].languages.map((l) => l.target_language)).toEqual(['de', 'en', 'ja'])
  })
})
