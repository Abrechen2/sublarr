/**
 * SeriesSettingsPanel — unit tests for the 0.71.1 cleanup_foreign_tracks
 * three-state toggle added to the subtitles section, and Phase A
 * "Subtitle settings →" navigation button.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SeriesSettingsPanel } from '../SeriesSettingsPanel'
import type { SeriesDetail } from '@/lib/types'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
  }),
}))

vi.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

const mockMutateAsync = vi.fn().mockResolvedValue({ created: true })
vi.mock('@/pages/Settings/profilesOverrides/useProfilesOverrides', () => ({
  useCreateOverride: () => ({ mutateAsync: mockMutateAsync, isPending: false }),
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

describe('SeriesSettingsPanel — subtitle settings button (Phase A)', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    mockMutateAsync.mockClear()
  })

  it('renders the subtitle settings button', () => {
    const series = makeSeries()
    render(
      <MemoryRouter>
        <SeriesSettingsPanel {...baseProps} series={series} />
      </MemoryRouter>,
    )
    expect(screen.getByTestId('series-subtitle-settings-link')).toBeInTheDocument()
  })

  it('calls createOverride and navigates to profiles page on click', async () => {
    const series = makeSeries()
    render(
      <MemoryRouter>
        <SeriesSettingsPanel {...baseProps} seriesId={42} series={series} />
      </MemoryRouter>,
    )
    fireEvent.click(screen.getByTestId('series-subtitle-settings-link'))
    await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledWith(42))
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith(
        expect.stringContaining('scope=series%3A42'),
      )
    )
  })
})
