/**
 * SeriesSettingsPanel — unit tests for the 0.71.1 cleanup_foreign_tracks
 * three-state toggle added to the subtitles section.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SeriesSettingsPanel } from '../SeriesSettingsPanel'
import type { SeriesDetail } from '@/lib/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
  }),
}))

vi.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

function makeSeries(overrides: Partial<SeriesDetail> = {}): SeriesDetail {
  return {
    id: 1,
    title: 'Test',
    year: 2024,
    path: '/media/test',
    poster: '',
    fanart: '',
    overview: '',
    status: 'continuing',
    season_count: 1,
    episode_count: 0,
    episode_file_count: 0,
    tags: [],
    profile_name: 'Default',
    target_languages: ['de'],
    target_language_names: ['German'],
    source_language: 'en',
    source_language_name: 'English',
    episodes: [],
    absolute_order: false,
    ...overrides,
  }
}

const baseProps = {
  seriesId: 1,
  showGlossary: false,
  hasFansubOverride: false,
  isExtracting: false,
  extractProgress: null,
  onToggleGlossary: vi.fn(),
  onToggleAbsoluteOrder: vi.fn(),
  onSetCleanupForeignTracks: vi.fn(),
  onRefreshAnidb: vi.fn(),
  onExtract: vi.fn(),
  onCleanup: vi.fn(),
  onFansub: vi.fn(),
  onExport: vi.fn(),
  updatePending: false,
  refreshPending: false,
}

describe('SeriesSettingsPanel — cleanup_foreign_tracks three-state toggle', () => {
  it('renders the cleanup select with "Inherit" preselected when override is null', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    render(<SeriesSettingsPanel {...baseProps} series={series} />)

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    expect((select as HTMLSelectElement).value).toBe('null')
  })

  it('preselects "Always" when override is true', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: true,
      cleanup_foreign_tracks_effective: true,
    })
    render(<SeriesSettingsPanel {...baseProps} series={series} />)

    expect(
      (screen.getByRole('combobox', { name: /cleanup foreign tracks/i }) as HTMLSelectElement)
        .value,
    ).toBe('true')
  })

  it('preselects "Never" when override is false', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: false,
      cleanup_foreign_tracks_effective: false,
    })
    render(<SeriesSettingsPanel {...baseProps} series={series} />)

    expect(
      (screen.getByRole('combobox', { name: /cleanup foreign tracks/i }) as HTMLSelectElement)
        .value,
    ).toBe('false')
  })

  it('calls onSetCleanupForeignTracks(true) when user selects "Always"', () => {
    const onSetCleanupForeignTracks = vi.fn()
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    render(
      <SeriesSettingsPanel
        {...baseProps}
        series={series}
        onSetCleanupForeignTracks={onSetCleanupForeignTracks}
      />,
    )

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    fireEvent.change(select, { target: { value: 'true' } })

    expect(onSetCleanupForeignTracks).toHaveBeenCalledWith(true)
  })

  it('calls onSetCleanupForeignTracks(null) when user selects "Inherit"', () => {
    const onSetCleanupForeignTracks = vi.fn()
    const series = makeSeries({
      cleanup_foreign_tracks_override: true,
      cleanup_foreign_tracks_effective: true,
    })
    render(
      <SeriesSettingsPanel
        {...baseProps}
        series={series}
        onSetCleanupForeignTracks={onSetCleanupForeignTracks}
      />,
    )

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    fireEvent.change(select, { target: { value: 'null' } })

    expect(onSetCleanupForeignTracks).toHaveBeenCalledWith(null)
  })

  it('disables the select while updatePending is true', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    render(<SeriesSettingsPanel {...baseProps} series={series} updatePending />)

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    expect((select as HTMLSelectElement).disabled).toBe(true)
  })
})
