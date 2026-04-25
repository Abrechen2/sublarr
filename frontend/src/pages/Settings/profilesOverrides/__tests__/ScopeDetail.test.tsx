import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScopeDetail } from '../ScopeDetail'
import type { ResolvedSettings } from '@/api/profilesOverrides'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

function buildResolved(): ResolvedSettings {
  const settings: Record<string, { effective: unknown; source: 'global' | 'profile' | 'series' | 'movie'; chain: { scope: 'global' | 'profile' | 'series' | 'movie'; value: unknown; label: string }[] }> = {}
  for (const key of [
    'cleanup_foreign_tracks', 'forced_preference', 'hi_preference', 'forced_scoring',
    'target_languages', 'cutoff_language', 'must_contain', 'must_not_contain',
    'audio_exclude_languages', 'preferred_audio_track_index', 'priority_override',
    'min_attempts_per_day',
  ]) {
    settings[key] = {
      effective: null, source: 'global',
      chain: [{ scope: 'global', value: null, label: 'Global default' }],
    }
  }
  return {
    scope: { type: 'series', id: 1, name: 'Frieren' },
    settings,
  }
}

describe('ScopeDetail', () => {
  it('renders all 12 inheritance rows', () => {
    render(<ScopeDetail resolved={buildResolved()} onChange={() => {}} onReset={() => {}} />)
    const rows = screen.getAllByTestId('inheritance-row')
    expect(rows).toHaveLength(12)
  })

  it('shows reset button only for series/movie scope', () => {
    render(<ScopeDetail resolved={buildResolved()} onChange={() => {}} onReset={() => {}} />)
    expect(screen.getByRole('button', { name: /reset all overrides/i })).toBeInTheDocument()
  })

  it('hides reset button for global scope', () => {
    const r = buildResolved()
    r.scope = { type: 'global', id: null, name: 'Global default' }
    render(<ScopeDetail resolved={r} onChange={() => {}} onReset={() => {}} />)
    expect(screen.queryByRole('button', { name: /reset all overrides/i })).toBeNull()
  })
})
