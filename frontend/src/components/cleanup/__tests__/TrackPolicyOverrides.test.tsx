/**
 * TrackPolicyOverrides — shared track-variant-policy override row, used by
 * both SeriesSettingsPanel (scope="series") and MovieDetail's subtitle
 * settings card (scope="movie"). Owner-approved spec 2026-09-25: series AND
 * movies get the same four overrides.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TrackPolicyOverrides } from '../TrackPolicyOverrides'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: unknown) =>
      typeof opts === 'string'
        ? opts
        : ((opts as { defaultValue?: string })?.defaultValue ?? _key),
  }),
}))

const mockGetResolvedSeriesSettings = vi.fn()
const mockGetResolvedMovieSettings = vi.fn()
const mockPatchSeriesTrackVariantOverride = vi.fn()
const mockPatchMovieTrackVariantOverride = vi.fn()
vi.mock('@/api/seriesSettings', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/seriesSettings')>()
  return {
    ...actual,
    getResolvedSeriesSettings: (...args: unknown[]) => mockGetResolvedSeriesSettings(...args),
    getResolvedMovieSettings: (...args: unknown[]) => mockGetResolvedMovieSettings(...args),
    patchSeriesTrackVariantOverride: (...args: unknown[]) =>
      mockPatchSeriesTrackVariantOverride(...args),
    patchMovieTrackVariantOverride: (...args: unknown[]) =>
      mockPatchMovieTrackVariantOverride(...args),
  }
})

function emptyResolvedSettings(id: number, scopeType: 'series' | 'movie') {
  const field = (value: unknown = null) => ({
    effective: value,
    source: 'global' as const,
    chain: [
      { scope: 'global' as const, value: null, label: 'Global default' },
      { scope: scopeType, value, label: `This ${scopeType}` },
    ],
  })
  return Promise.resolve({
    scope: { type: scopeType, id, name: 'Test' },
    settings: {
      cleanup_track_variant_mode: field(),
      cleanup_keep_forced: field(),
      cleanup_keep_sdh: field(),
      cleanup_sidecar_policy: field(),
    },
  })
}

function renderWithClient(children: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  })
  return render(<QueryClientProvider client={queryClient}>{children}</QueryClientProvider>)
}

describe('TrackPolicyOverrides', () => {
  beforeEach(() => {
    mockGetResolvedSeriesSettings.mockReset()
    mockGetResolvedMovieSettings.mockReset()
    mockPatchSeriesTrackVariantOverride.mockReset().mockResolvedValue({ ok: true })
    mockPatchMovieTrackVariantOverride.mockReset().mockResolvedValue({ ok: true })
  })

  describe('scope="series"', () => {
    beforeEach(() => {
      mockGetResolvedSeriesSettings.mockImplementation((id: number) =>
        emptyResolvedSettings(id, 'series'),
      )
    })

    it('reads through getResolvedSeriesSettings, not the movie resolver', async () => {
      renderWithClient(<TrackPolicyOverrides scope="series" id={5} />)
      await waitFor(() => expect(mockGetResolvedSeriesSettings).toHaveBeenCalledWith(5))
      expect(mockGetResolvedMovieSettings).not.toHaveBeenCalled()
    })

    it('sends null (inherit) via patchSeriesTrackVariantOverride, not the movie endpoint', async () => {
      renderWithClient(<TrackPolicyOverrides scope="series" id={5} />)
      const select = screen.getByRole('combobox', { name: 'Variants per language override' })
      fireEvent.change(select, { target: { value: 'one_per_language' } })
      await waitFor(() =>
        expect(mockPatchSeriesTrackVariantOverride).toHaveBeenCalledWith(5, {
          cleanup_track_variant_mode: 'one_per_language',
        }),
      )

      fireEvent.change(select, { target: { value: 'null' } })
      await waitFor(() =>
        expect(mockPatchSeriesTrackVariantOverride).toHaveBeenLastCalledWith(5, {
          cleanup_track_variant_mode: null,
        }),
      )
      expect(mockPatchMovieTrackVariantOverride).not.toHaveBeenCalled()
    })
  })

  describe('scope="movie"', () => {
    beforeEach(() => {
      mockGetResolvedMovieSettings.mockImplementation((id: number) =>
        emptyResolvedSettings(id, 'movie'),
      )
    })

    it('reads through getResolvedMovieSettings, not the series resolver', async () => {
      renderWithClient(<TrackPolicyOverrides scope="movie" id={9} />)
      await waitFor(() => expect(mockGetResolvedMovieSettings).toHaveBeenCalledWith(9))
      expect(mockGetResolvedSeriesSettings).not.toHaveBeenCalled()
    })

    it('PATCH hits /profiles-overrides/movie/<id> via patchMovieTrackVariantOverride', async () => {
      // Sidecar policy is only enabled in "one_per_language" mode — seed a
      // resolved response with that effective mode for this test.
      mockGetResolvedMovieSettings.mockResolvedValue({
        scope: { type: 'movie', id: 9, name: 'Test' },
        settings: {
          cleanup_track_variant_mode: {
            effective: 'one_per_language',
            source: 'movie',
            chain: [{ scope: 'movie', value: 'one_per_language', label: 'This movie' }],
          },
          cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
          cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
          cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
        },
      })
      renderWithClient(<TrackPolicyOverrides scope="movie" id={9} />)
      const select = await screen.findByRole('combobox', { name: 'Sidecar policy override' })
      await waitFor(() => expect(select).not.toBeDisabled())

      fireEvent.change(select, { target: { value: 'drop_if_real_sidecar' } })
      await waitFor(() =>
        expect(mockPatchMovieTrackVariantOverride).toHaveBeenCalledWith(9, {
          cleanup_sidecar_policy: 'drop_if_real_sidecar',
        }),
      )
      expect(mockPatchSeriesTrackVariantOverride).not.toHaveBeenCalled()
    })

    it('disables keep_forced/keep_sdh/sidecar_policy when the effective mode is "all"', async () => {
      mockGetResolvedMovieSettings.mockResolvedValue({
        scope: { type: 'movie', id: 9, name: 'Test' },
        settings: {
          cleanup_track_variant_mode: { effective: 'all', source: 'global', chain: [] },
          cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
          cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
          cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
        },
      })
      renderWithClient(<TrackPolicyOverrides scope="movie" id={9} />)

      await waitFor(() =>
        expect(screen.getByRole('combobox', { name: 'Keep forced override' })).toBeDisabled(),
      )
      expect(screen.getByRole('combobox', { name: 'Keep SDH override' })).toBeDisabled()
      expect(screen.getByRole('combobox', { name: 'Sidecar policy override' })).toBeDisabled()
      // Mode select itself is never gated by policy B.
      expect(screen.getByRole('combobox', { name: 'Variants per language override' })).not.toBeDisabled()
    })

    it('enables keep_forced/keep_sdh/sidecar_policy when the effective mode is "one_per_language"', async () => {
      mockGetResolvedMovieSettings.mockResolvedValue({
        scope: { type: 'movie', id: 9, name: 'Test' },
        settings: {
          cleanup_track_variant_mode: {
            effective: 'one_per_language',
            source: 'movie',
            chain: [{ scope: 'movie', value: 'one_per_language', label: 'This movie' }],
          },
          cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
          cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
          cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
        },
      })
      renderWithClient(<TrackPolicyOverrides scope="movie" id={9} />)

      await waitFor(() =>
        expect(screen.getByRole('combobox', { name: 'Keep forced override' })).not.toBeDisabled(),
      )
      expect(screen.getByRole('combobox', { name: 'Keep SDH override' })).not.toBeDisabled()
      expect(screen.getByRole('combobox', { name: 'Sidecar policy override' })).not.toBeDisabled()
    })

    it('sends null (inherit) for cleanup_keep_sdh via the movie endpoint', async () => {
      mockGetResolvedMovieSettings.mockResolvedValue({
        scope: { type: 'movie', id: 9, name: 'Test' },
        settings: {
          cleanup_track_variant_mode: {
            effective: 'one_per_language',
            source: 'movie',
            chain: [{ scope: 'movie', value: 'one_per_language', label: 'This movie' }],
          },
          cleanup_keep_forced: { effective: true, source: 'global', chain: [] },
          cleanup_keep_sdh: { effective: false, source: 'global', chain: [] },
          cleanup_sidecar_policy: { effective: 'keep_embedded', source: 'global', chain: [] },
        },
      })
      renderWithClient(<TrackPolicyOverrides scope="movie" id={9} />)
      const select = await screen.findByRole('combobox', { name: 'Keep SDH override' })
      await waitFor(() => expect(select).not.toBeDisabled())

      fireEvent.change(select, { target: { value: 'true' } })
      await waitFor(() =>
        expect(mockPatchMovieTrackVariantOverride).toHaveBeenCalledWith(9, {
          cleanup_keep_sdh: true,
        }),
      )

      fireEvent.change(select, { target: { value: 'null' } })
      await waitFor(() =>
        expect(mockPatchMovieTrackVariantOverride).toHaveBeenLastCalledWith(9, {
          cleanup_keep_sdh: null,
        }),
      )
    })
  })
})
