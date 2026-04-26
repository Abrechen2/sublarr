/**
 * SeriesSettingsPanel — unit tests for the 0.71.1 cleanup_foreign_tracks
 * three-state toggle and the per-series profile selector.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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

const mockAssignMutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useLanguageProfiles: () => ({
    data: [
      { id: 1, name: 'Default', is_default: true },
      { id: 2, name: 'German Only', is_default: false },
    ],
  }),
  useAssignProfile: () => ({ mutate: mockAssignMutate, isPending: false }),
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
    profile_id: 1,
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
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    expect((select as HTMLSelectElement).value).toBe('null')
  })

  it('preselects "Always" when override is true', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: true,
      cleanup_foreign_tracks_effective: true,
    })
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)

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
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)

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
      <MemoryRouter>
        <SeriesSettingsPanel
          {...baseProps}
          series={series}
          onSetCleanupForeignTracks={onSetCleanupForeignTracks}
        />
      </MemoryRouter>,
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
      <MemoryRouter>
        <SeriesSettingsPanel
          {...baseProps}
          series={series}
          onSetCleanupForeignTracks={onSetCleanupForeignTracks}
        />
      </MemoryRouter>,
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
    render(
      <MemoryRouter>
        <SeriesSettingsPanel {...baseProps} series={series} updatePending />
      </MemoryRouter>,
    )

    const select = screen.getByRole('combobox', { name: /cleanup foreign tracks/i })
    expect((select as HTMLSelectElement).disabled).toBe(true)
  })
})

describe('SeriesSettingsPanel — profile selector (Phase B)', () => {
  beforeEach(() => {
    mockAssignMutate.mockClear()
  })

  it('renders a profile select dropdown', () => {
    const series = makeSeries({ profile_id: 1, profile_name: 'Default' })
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)
    expect(screen.getByTestId('series-profile-select')).toBeInTheDocument()
  })

  it('pre-selects the current profile_id', () => {
    const series = makeSeries({ profile_id: 2, profile_name: 'German Only' })
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)
    const select = screen.getByTestId('series-profile-select') as HTMLSelectElement
    expect(select.value).toBe('2')
  })

  it('renders default profile with star suffix', () => {
    const series = makeSeries({ profile_id: 1 })
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} series={series} /></MemoryRouter>)
    expect(screen.getByText('Default ★')).toBeInTheDocument()
  })

  it('calls useAssignProfile.mutate with correct args on change', () => {
    const series = makeSeries({ profile_id: 1 })
    render(<MemoryRouter><SeriesSettingsPanel {...baseProps} seriesId={7} series={series} /></MemoryRouter>)
    const select = screen.getByTestId('series-profile-select')
    fireEvent.change(select, { target: { value: '2' } })
    expect(mockAssignMutate).toHaveBeenCalledWith({ type: 'series', arrId: 7, profileId: 2 })
  })
})

