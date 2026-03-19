import { describe, it, expect } from 'vitest'
import { NAV_GROUPS } from '../pages/Settings/index'

describe('Settings NAV_GROUPS structure', () => {
  it('has exactly 5 top-level groups', () => {
    expect(NAV_GROUPS).toHaveLength(5)
  })

  it('Connections group contains expected tabs', () => {
    const g = NAV_GROUPS.find(g => g.title === 'Connections')
    expect(g).toBeDefined()
    expect(g!.items).toContain('Sonarr')
    expect(g!.items).toContain('Radarr')
    expect(g!.items).toContain('API Keys')
  })

  it('Languages & Subtitles group contains expected tabs', () => {
    const g = NAV_GROUPS.find(g => g.title === 'Languages & Subtitles')
    expect(g).toBeDefined()
    expect(g!.items).toContain('Languages')
    expect(g!.items).toContain('Scoring')
  })

  it('Providers group exists', () => {
    const g = NAV_GROUPS.find(g => g.title === 'Providers')
    expect(g).toBeDefined()
    expect(g!.items).toContain('Providers')
  })

  it('Automation group contains Translation tabs', () => {
    const g = NAV_GROUPS.find(g => g.title === 'Automation')
    expect(g).toBeDefined()
    expect(g!.items).toContain('Automation')
    expect(g!.items).toContain('Translation')
    expect(g!.items).toContain('Whisper')
  })

  it('System group contains Protokoll', () => {
    const g = NAV_GROUPS.find(g => g.title === 'System')
    expect(g).toBeDefined()
    expect(g!.items).toContain('Events & Hooks')
    expect(g!.items).toContain('Backup')
    expect(g!.items).toContain('Security')
    expect(g!.items).toContain('Protokoll')
  })

  it('contains all 23 original tabs — none lost', () => {
    const all = NAV_GROUPS.flatMap(g => g.items)
    const expected = [
      'General', 'API Keys',
      'Sonarr', 'Radarr', 'Library Sources', 'Media Servers',
      'Translation', 'Translation Backends', 'Prompt Presets', 'Languages',
      'Automation', 'Wanted', 'Whisper',
      'Providers', 'Scoring',
      'Events & Hooks', 'Backup', 'Subtitle Tools', 'Cleanup',
      'Integrations', 'Notification Templates', 'Security', 'Protokoll',
    ]
    for (const tab of expected) {
      expect(all, `Missing tab: ${tab}`).toContain(tab)
    }
  })
})
