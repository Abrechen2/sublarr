import { describe, it, expect } from 'vitest'
import { searchSettings, SETTINGS_REGISTRY } from '../settingsRegistry'

describe('SETTINGS_REGISTRY', () => {
  it('has entries for all 8 categories', () => {
    const categories = new Set(SETTINGS_REGISTRY.map((e) => e.category))
    expect(categories).toContain('General')
    expect(categories).toContain('Connections')
    expect(categories).toContain('Subtitles')
    expect(categories).toContain('Providers')
    expect(categories).toContain('Automation')
    expect(categories).toContain('Translation')
    expect(categories).toContain('Notifications')
    expect(categories).toContain('System')
  })

  it('each entry has required fields', () => {
    for (const entry of SETTINGS_REGISTRY) {
      expect(entry.id).toBeTruthy()
      expect(entry.label).toBeTruthy()
      expect(entry.keywords.length).toBeGreaterThan(0)
      expect(entry.category).toBeTruthy()
      expect(entry.route).toMatch(/^\/settings\//)
    }
  })

  it('has unique IDs', () => {
    const ids = SETTINGS_REGISTRY.map((e) => e.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('searchSettings', () => {
  it('returns empty array for empty query', () => {
    expect(searchSettings('')).toEqual([])
    expect(searchSettings('   ')).toEqual([])
  })

  it('finds settings by label', () => {
    const results = searchSettings('sonarr')
    expect(results.length).toBeGreaterThan(0)
    expect(results.some((r) => r.id === 'sonarr')).toBe(true)
  })

  it('finds settings by keyword', () => {
    const results = searchSettings('ollama')
    expect(results.length).toBeGreaterThan(0)
    expect(results.some((r) => r.category === 'Translation')).toBe(true)
  })

  it('finds settings by keyword case-insensitively', () => {
    const results = searchSettings('SONARR')
    expect(results.length).toBeGreaterThan(0)
  })

  it('supports multi-word queries (AND logic)', () => {
    const results = searchSettings('auto upgrade')
    expect(results.length).toBeGreaterThan(0)
    expect(results.some((r) => r.id === 'auto-upgrade')).toBe(true)
  })

  it('returns empty for non-matching query', () => {
    expect(searchSettings('xyznonexistent')).toEqual([])
  })

  it('finds German keywords', () => {
    const results = searchSettings('sprache')
    expect(results.length).toBeGreaterThan(0)
    expect(results.some((r) => r.id === 'language')).toBe(true)
  })
})
