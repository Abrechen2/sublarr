import { describe, it, expect } from 'vitest'
import { buildOnboardingPayload } from '../pages/Onboarding'

// The wizard's initial values (Onboarding.tsx), with a Sonarr filled in.
const VALUES = {
  sonarr_url: 'http://192.168.10.40:8989',
  sonarr_api_key: 'abc',
  radarr_url: '',
  radarr_api_key: '',
  path_mapping: '/data/media=/media',
  opensubtitles_api_key: '',
  jimaku_api_key: '',
  subdl_api_key: '',
  ollama_url: 'http://localhost:11434',
  ollama_model: 'qwen2.5:14b-instruct',
  target_language: 'de',
  target_language_name: 'German',
  source_language: 'en',
  source_language_name: 'English',
  tmdb_api_key: 'tmdb',
  tvdb_api_key: '',
  automation_enabled: 'true',
  search_interval_hours: '6',
  upgrade_enabled: 'true',
}

// Discord install-help 2026-10-31: 1.18.3 refused every wizard step with
// "Unknown config key: automation_enabled", and the untouched Ollama default
// as a loopback URL, so nothing from the wizard (path mapping included) was saved.
describe('buildOnboardingPayload', () => {
  it('sends no wizard-only keys', () => {
    const payload = buildOnboardingPayload(VALUES, 'arr')

    expect(payload).not.toHaveProperty('automation_enabled')
    expect(payload).not.toHaveProperty('search_interval_hours')
  })

  it('saves the automation choice as the wanted-search interval', () => {
    expect(buildOnboardingPayload(VALUES, 'arr').wanted_search_interval_hours).toBe('6')
    expect(
      buildOnboardingPayload({ ...VALUES, automation_enabled: 'false' }, 'arr').wanted_search_interval_hours,
    ).toBe('0')
  })

  it('leaves the untouched loopback Ollama default out', () => {
    expect(buildOnboardingPayload(VALUES, 'arr')).not.toHaveProperty('ollama_url')
    expect(
      buildOnboardingPayload({ ...VALUES, ollama_url: 'http://ollama:11434' }, 'arr').ollama_url,
    ).toBe('http://ollama:11434')
  })

  it('keeps the path mapping and drops the other mode and empty values', () => {
    const arr = buildOnboardingPayload(VALUES, 'arr')
    expect(arr.path_mapping).toBe('/data/media=/media')
    expect(arr).not.toHaveProperty('tmdb_api_key')
    expect(arr).not.toHaveProperty('radarr_url')

    const standalone = buildOnboardingPayload(VALUES, 'standalone')
    expect(standalone).not.toHaveProperty('sonarr_url')
    expect(standalone).not.toHaveProperty('path_mapping')
    expect(standalone.tmdb_api_key).toBe('tmdb')
  })
})
