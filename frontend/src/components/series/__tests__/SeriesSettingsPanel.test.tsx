/**
 * SeriesSettingsPanel — unit tests for the 0.71.1 cleanup_foreign_tracks
 * three-state toggle, the per-series profile selector, and the 1.15.0
 * track variant policy overrides (profiles-overrides API).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SeriesSettingsPanel } from '../SeriesSettingsPanel'
import type { SeriesDetail } from '@/lib/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: unknown) =>
      typeof opts === 'string'
        ? opts
        : ((opts as { defaultValue?: string })?.defaultValue ?? _key),
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

// ─── Track variant policy overrides API (1.15.0) ────────────────────────────
const mockGetResolvedSeriesSettings = vi.fn()
const mockPatchSeriesTrackVariantOverride = vi.fn()
vi.mock('@/api/seriesSettings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/seriesSettings')>()
  return {
    ...actual,
    getResolvedSeriesSettings: (...args: unknown[]) => mockGetResolvedSeriesSettings(...args),
    patchSeriesTrackVariantOverride: (...args: unknown[]) =>
      mockPatchSeriesTrackVariantOverride(...args),
  }
})

const mockPreviewFile = vi.fn()
vi.mock('@/api/foreignTracks', () => ({
  previewFile: (...args: unknown[]) => mockPreviewFile(...args),
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
  onScanHealth: vi.fn(),
  updatePending: false,
  refreshPending: false,
}

/** Fresh QueryClient per render — the panel now fetches the resolved
 * track-variant settings via react-query, so every test needs a provider. */
function renderPanel(children: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function emptyResolvedSettings(seriesId: number) {
  const field = (value: unknown = null) => ({
    effective: value,
    source: 'global' as const,
    chain: [
      { scope: 'global' as const, value: null, label: 'Global default' },
      { scope: 'series' as const, value, label: 'This series' },
    ],
  })
  return Promise.resolve({
    scope: { type: 'series', id: seriesId, name: 'Test' },
    settings: {
      cleanup_track_variant_mode: field(),
      cleanup_keep_forced: field(),
      cleanup_keep_sdh: field(),
      cleanup_sidecar_policy: field(),
    },
  })
}

describe('SeriesSettingsPanel — cleanup_foreign_tracks three-state toggle', () => {
  beforeEach(() => {
    mockGetResolvedSeriesSettings.mockReset().mockImplementation(emptyResolvedSettings)
    mockPatchSeriesTrackVariantOverride.mockReset().mockResolvedValue({ ok: true })
  })

  it('renders the cleanup select with "Inherit" preselected when override is null', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    const select = screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i })
    expect((select as HTMLSelectElement).value).toBe('null')
  })

  it('preselects "Always" when override is true', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: true,
      cleanup_foreign_tracks_effective: true,
    })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    expect(
      (screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i }) as HTMLSelectElement)
        .value,
    ).toBe('true')
  })

  it('preselects "Never" when override is false', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: false,
      cleanup_foreign_tracks_effective: false,
    })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    expect(
      (screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i }) as HTMLSelectElement)
        .value,
    ).toBe('false')
  })

  it('calls onSetCleanupForeignTracks(true) when user selects "Always"', () => {
    const onSetCleanupForeignTracks = vi.fn()
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    renderPanel(
      <SeriesSettingsPanel
        {...baseProps}
        series={series}
        onSetCleanupForeignTracks={onSetCleanupForeignTracks}
      />,
    )

    const select = screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i })
    fireEvent.change(select, { target: { value: 'true' } })

    expect(onSetCleanupForeignTracks).toHaveBeenCalledWith(true)
  })

  it('calls onSetCleanupForeignTracks(null) when user selects "Inherit"', () => {
    const onSetCleanupForeignTracks = vi.fn()
    const series = makeSeries({
      cleanup_foreign_tracks_override: true,
      cleanup_foreign_tracks_effective: true,
    })
    renderPanel(
      <SeriesSettingsPanel
        {...baseProps}
        series={series}
        onSetCleanupForeignTracks={onSetCleanupForeignTracks}
      />,
    )

    const select = screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i })
    fireEvent.change(select, { target: { value: 'null' } })

    expect(onSetCleanupForeignTracks).toHaveBeenCalledWith(null)
  })

  it('disables the select while updatePending is true', () => {
    const series = makeSeries({
      cleanup_foreign_tracks_override: null,
      cleanup_foreign_tracks_effective: false,
    })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} updatePending />)

    const select = screen.getByRole('combobox', { name: /cleanup_foreign_tracks/i })
    expect((select as HTMLSelectElement).disabled).toBe(true)
  })
})

describe('SeriesSettingsPanel — profile selector (Phase B)', () => {
  beforeEach(() => {
    mockAssignMutate.mockClear()
    mockGetResolvedSeriesSettings.mockReset().mockImplementation(emptyResolvedSettings)
    mockPatchSeriesTrackVariantOverride.mockReset().mockResolvedValue({ ok: true })
  })

  it('renders a profile select dropdown', () => {
    const series = makeSeries({ profile_id: 1, profile_name: 'Default' })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)
    expect(screen.getByTestId('series-profile-select')).toBeInTheDocument()
  })

  it('pre-selects the current profile_id', () => {
    const series = makeSeries({ profile_id: 2, profile_name: 'German Only' })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)
    const select = screen.getByTestId('series-profile-select') as HTMLSelectElement
    expect(select.value).toBe('2')
  })

  it('renders default profile with star suffix', () => {
    const series = makeSeries({ profile_id: 1 })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)
    expect(screen.getByText('Default ★')).toBeInTheDocument()
  })

  it('calls useAssignProfile.mutate with correct args on change', () => {
    const series = makeSeries({ profile_id: 1 })
    renderPanel(<SeriesSettingsPanel {...baseProps} seriesId={7} series={series} />)
    const select = screen.getByTestId('series-profile-select')
    fireEvent.change(select, { target: { value: '2' } })
    expect(mockAssignMutate).toHaveBeenCalledWith({ type: 'series', arrId: 7, profileId: 2 })
  })
})

// ─── 1.15.0 — track variant policy overrides ────────────────────────────────
describe('SeriesSettingsPanel — track variant policy overrides', () => {
  beforeEach(() => {
    mockGetResolvedSeriesSettings.mockReset().mockImplementation(emptyResolvedSettings)
    mockPatchSeriesTrackVariantOverride.mockReset().mockResolvedValue({ ok: true })
    mockPreviewFile.mockReset()
  })

  it('sends null (inherit) for cleanup_track_variant_mode when the user picks "Inherit"', async () => {
    const series = makeSeries()
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    const select = screen.getByRole('combobox', {
      name: 'Variants per language override',
    }) as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'one_per_language' } })
    await waitFor(() =>
      expect(mockPatchSeriesTrackVariantOverride).toHaveBeenCalledWith(1, {
        cleanup_track_variant_mode: 'one_per_language',
      }),
    )

    // Now pick "Inherit" — this is the change under test.
    fireEvent.change(select, { target: { value: 'null' } })
    await waitFor(() =>
      expect(mockPatchSeriesTrackVariantOverride).toHaveBeenLastCalledWith(1, {
        cleanup_track_variant_mode: null,
      }),
    )
  })

  it('sends null (inherit) for cleanup_keep_forced when the user picks "Inherit"', async () => {
    // keep_forced is only interactive in "one_per_language" mode — resolve
    // the effective mode as such so the control isn't disabled.
    mockGetResolvedSeriesSettings.mockResolvedValue({
      scope: { type: 'series', id: 1, name: 'Test' },
      settings: {
        cleanup_track_variant_mode: {
          effective: 'one_per_language',
          source: 'series',
          chain: [{ scope: 'series', value: 'one_per_language', label: 'This series' }],
        },
        cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
        cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
        cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
      },
    })
    const series = makeSeries()
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    const select = await screen.findByRole('combobox', { name: 'Keep forced override' })
    await waitFor(() => expect(select).not.toBeDisabled())
    fireEvent.change(select, { target: { value: 'true' } })
    await waitFor(() =>
      expect(mockPatchSeriesTrackVariantOverride).toHaveBeenCalledWith(1, {
        cleanup_keep_forced: true,
      }),
    )

    fireEvent.change(select, { target: { value: 'null' } })
    await waitFor(() =>
      expect(mockPatchSeriesTrackVariantOverride).toHaveBeenLastCalledWith(1, {
        cleanup_keep_forced: null,
      }),
    )
  })

  it('sends a concrete value for cleanup_sidecar_policy when the user picks an option', async () => {
    mockGetResolvedSeriesSettings.mockResolvedValue({
      scope: { type: 'series', id: 1, name: 'Test' },
      settings: {
        cleanup_track_variant_mode: {
          effective: 'one_per_language',
          source: 'series',
          chain: [{ scope: 'series', value: 'one_per_language', label: 'This series' }],
        },
        cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
        cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
        cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
      },
    })
    const series = makeSeries()
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    const select = await screen.findByRole('combobox', { name: 'Sidecar policy override' })
    await waitFor(() => expect(select).not.toBeDisabled())
    fireEvent.change(select, { target: { value: 'drop_if_real_sidecar' } })

    await waitFor(() =>
      expect(mockPatchSeriesTrackVariantOverride).toHaveBeenLastCalledWith(1, {
        cleanup_sidecar_policy: 'drop_if_real_sidecar',
      }),
    )
  })

  it('disables keep_forced, keep_sdh and sidecar_policy when the effective mode is "all"', async () => {
    mockGetResolvedSeriesSettings.mockResolvedValue({
      scope: { type: 'series', id: 1, name: 'Test' },
      settings: {
        cleanup_track_variant_mode: {
          effective: 'all',
          source: 'global',
          chain: [
            { scope: 'global', value: 'all', label: 'Global default' },
            { scope: 'series', value: null, label: 'This series' },
          ],
        },
        cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
        cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
        cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
      },
    })
    const series = makeSeries()
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    expect(await screen.findByRole('combobox', { name: 'Keep forced override' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Keep SDH override' })).toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Sidecar policy override' })).toBeDisabled()
  })

  it('enables keep_forced, keep_sdh and sidecar_policy when the effective mode is "one_per_language"', async () => {
    mockGetResolvedSeriesSettings.mockResolvedValue({
      scope: { type: 'series', id: 1, name: 'Test' },
      settings: {
        cleanup_track_variant_mode: {
          effective: 'one_per_language',
          source: 'series',
          chain: [
            { scope: 'global', value: 'all', label: 'Global default' },
            { scope: 'series', value: 'one_per_language', label: 'This series' },
          ],
        },
        cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
        cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
        cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
      },
    })
    const series = makeSeries()
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Keep forced override' })).not.toBeDisabled(),
    )
    expect(screen.getByRole('combobox', { name: 'Keep SDH override' })).not.toBeDisabled()
    expect(screen.getByRole('combobox', { name: 'Sidecar policy override' })).not.toBeDisabled()
  })

  it('renders the episode picker and preview verdicts after clicking preview', async () => {
    mockPreviewFile.mockResolvedValue({
      path: '/media/test/S01E01.mkv',
      policy: { mode: 'one_per_language', keep_forced: true, keep_sdh: false, sidecar_policy: 'keep_embedded' },
      verdicts: [
        { index: 2, sub_index: 0, language: 'en', fmt: 'ass', kind: 'full', keep: true, reason: 'kept_main' },
      ],
    })
    const series = makeSeries({
      episodes: [
        {
          id: 101,
          season: 1,
          episode: 1,
          title: 'Pilot',
          has_file: true,
          file_path: '/media/test/S01E01.mkv',
          subtitles: {},
          audio_languages: [],
          monitored: true,
        },
      ],
    })
    renderPanel(<SeriesSettingsPanel {...baseProps} series={series} />)

    const previewButton = screen.getByRole('button', { name: 'Preview one episode' })
    fireEvent.click(previewButton)

    await waitFor(() =>
      expect(mockPreviewFile).toHaveBeenCalledWith({
        path: '/media/test/S01E01.mkv',
        series_id: 1,
      }),
    )
    expect(await screen.findByTestId('verdict-2')).toBeInTheDocument()
  })
})
