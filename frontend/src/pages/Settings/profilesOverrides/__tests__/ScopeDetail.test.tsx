import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ScopeDetail } from '../ScopeDetail'
import type { ResolvedSettings } from '@/api/profilesOverrides'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

function buildResolved(scopeType: 'global' | 'series' | 'movie' = 'series'): ResolvedSettings {
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
    scope: { type: scopeType, id: scopeType === 'global' ? null : 1, name: scopeType === 'global' ? 'Global default' : 'Frieren' },
    settings,
  }
}

function renderDetail(props: Partial<React.ComponentProps<typeof ScopeDetail>> & { resolved: ResolvedSettings } = { resolved: buildResolved() }) {
  return render(
    <MemoryRouter>
      <ScopeDetail
        onChange={() => {}}
        onReset={() => {}}
        {...props}
      />
    </MemoryRouter>
  )
}

describe('ScopeDetail', () => {
  it('renders all 12 inheritance rows', () => {
    renderDetail()
    const rows = screen.getAllByTestId('inheritance-row')
    expect(rows).toHaveLength(12)
  })

  it('shows reset button only for series/movie scope', () => {
    renderDetail()
    expect(screen.getByRole('button', { name: /reset all overrides/i })).toBeInTheDocument()
  })

  it('hides reset button for global scope', () => {
    renderDetail({ resolved: buildResolved('global') })
    expect(screen.queryByRole('button', { name: /reset all overrides/i })).toBeNull()
  })

  it('renders back-link when backHref is provided', () => {
    renderDetail({ resolved: buildResolved('series'), backHref: '/library/series/1' })
    const link = screen.getByTestId('scope-detail-back-link')
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/library/series/1')
  })

  it('does not render back-link when backHref is absent', () => {
    renderDetail({ resolved: buildResolved('series') })
    expect(screen.queryByTestId('scope-detail-back-link')).toBeNull()
  })

  it('renders remove button when onRemove is provided', () => {
    renderDetail({ resolved: buildResolved('series'), onRemove: vi.fn() })
    expect(screen.getByTestId('scope-detail-remove-btn')).toBeInTheDocument()
  })

  it('does not render remove button when onRemove is absent', () => {
    renderDetail({ resolved: buildResolved('series') })
    expect(screen.queryByTestId('scope-detail-remove-btn')).toBeNull()
  })

  it('calls onRemove after confirm dialog is accepted', () => {
    const onRemove = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderDetail({ resolved: buildResolved('series'), onRemove })
    fireEvent.click(screen.getByTestId('scope-detail-remove-btn'))
    expect(onRemove).toHaveBeenCalledOnce()
    vi.restoreAllMocks()
  })

  it('does not call onRemove when confirm dialog is cancelled', () => {
    const onRemove = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderDetail({ resolved: buildResolved('series'), onRemove })
    fireEvent.click(screen.getByTestId('scope-detail-remove-btn'))
    expect(onRemove).not.toHaveBeenCalled()
    vi.restoreAllMocks()
  })
})
