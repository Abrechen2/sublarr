/**
 * LanguageProfilesTab.test.tsx — Tests for the per-profile translation backend
 * override (Task 4): a profile can inherit the global default (empty) or
 * override with an explicit backend + optional single fallback.
 *
 * NOTE: `frontend/src/pages/__tests__/LanguageProfiles.test.tsx` tests the
 * *wrapper page* (`LanguageProfilesPage`) and mocks `LanguageProfilesTab` out
 * entirely via `vi.mock('../Settings/AdvancedTab', ...)` — it never renders
 * the real tab, so it cannot assert on form behavior or mutation payloads.
 * This dedicated test file exercises the real `LanguageProfilesTab` directly,
 * mirroring the mock/render pattern already used by
 * `TranslationTab.test.tsx` / `DefaultBackendSection.test.tsx` (mock
 * `@/hooks/useApi` with the hooks the component under test needs).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LanguageProfilesTab } from '../LanguageProfilesTab'
import type { LanguageProfile } from '@/lib/types'

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

const profile: LanguageProfile = {
  id: 1,
  name: 'Anime DE',
  source_language: 'ja',
  source_language_name: 'Japanese',
  target_languages: ['de', 'en'],
  target_language_names: ['German', 'English'],
  is_default: true,
  translation_backend: '',
  fallback_chain: [],
  forced_preference: 'disabled',
  forced_scoring: 'include',
  hi_preference: 'include',
  cutoff_language: '',
  combine_enabled: true,
  combine_format: 'srt',
  combine_languages: ['de', 'en'],
  combine_position: { primary: 'top', secondary: 'bottom' },
}

const updateMutate = vi.fn()
const createMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useLanguageProfiles: () => ({ data: [profile], isLoading: false }),
  useCreateProfile: () => ({ mutate: createMutate, isPending: false }),
  useUpdateProfile: () => ({ mutate: updateMutate, isPending: false }),
  useDeleteProfile: () => ({ mutate: vi.fn(), isPending: false }),
  useSetProfileAsDefaultForAll: () => ({ mutate: vi.fn(), isPending: false }),
  useBackends: () => ({
    data: {
      backends: [
        { name: 'ollama', display_name: 'Ollama (Local LLM)', configured: false },
        { name: 'deepl', display_name: 'DeepL', configured: true },
      ],
    },
  }),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function openEditor() {
  render(<LanguageProfilesTab />)
  fireEvent.click(screen.getByTitle('language_profiles.edit_profile'))
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('LanguageProfilesTab — per-profile backend override', () => {
  it('sends translation_backend + fallback_chain in the update payload', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })
    fireEvent.change(screen.getByTestId('profile-fallback'), { target: { value: 'ollama' } })

    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          translation_backend: 'deepl',
          fallback_chain: ['deepl', 'ollama'],
        }),
      }),
      expect.anything(),
    )
  })

  it('omits the fallback picker while the backend is set to inherit (empty)', () => {
    openEditor()
    expect(screen.queryByTestId('profile-fallback')).not.toBeInTheDocument()
  })

  it('sends an empty fallback_chain when the backend stays on inherit', () => {
    openEditor()

    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          translation_backend: '',
          fallback_chain: [],
        }),
      }),
      expect.anything(),
    )
  })

  it('collapses to a single-entry fallback_chain when primary and fallback match', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })
    fireEvent.change(screen.getByTestId('profile-fallback'), { target: { value: 'deepl' } })
    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          translation_backend: 'deepl',
          fallback_chain: ['deepl'],
        }),
      }),
      expect.anything(),
    )
  })
})

describe('LanguageProfilesTab — provisional MT re-seek controls', () => {
  it('hides mt_on_original_found and mt_min_original_score when mt_keep_seeking_original is off', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })

    expect(screen.queryByTestId('profile-mt-on-original-found')).not.toBeInTheDocument()
    expect(screen.queryByTestId('profile-mt-min-original-score')).not.toBeInTheDocument()
  })

  it('shows mt_on_original_found and mt_min_original_score once mt_keep_seeking_original is on', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })
    fireEvent.click(screen.getByTestId('profile-mt-keep-seeking'))

    expect(screen.getByTestId('profile-mt-on-original-found')).toBeInTheDocument()
    expect(screen.getByTestId('profile-mt-min-original-score')).toBeInTheDocument()
  })

  it('updates form state when the dropdown and score input change, and includes both in the save payload', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })
    fireEvent.click(screen.getByTestId('profile-mt-keep-seeking'))

    fireEvent.change(screen.getByTestId('profile-mt-on-original-found'), { target: { value: 'auto_replace' } })
    fireEvent.change(screen.getByTestId('profile-mt-min-original-score'), { target: { value: '5' } })

    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          mt_keep_seeking_original: true,
          mt_on_original_found: 'auto_replace',
          mt_min_original_score: 5,
        }),
      }),
      expect.anything(),
    )
  })

  it('defaults mt_on_original_found to notify and mt_min_original_score to 1 when saved without changes', () => {
    openEditor()

    fireEvent.change(screen.getByTestId('profile-backend'), { target: { value: 'deepl' } })
    fireEvent.click(screen.getByTestId('profile-mt-keep-seeking'))

    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          mt_keep_seeking_original: true,
          mt_on_original_found: 'notify',
          mt_min_original_score: 1,
        }),
      }),
      expect.anything(),
    )
  })
})

describe('LanguageProfilesTab — combined subtitles', () => {
  it('round-trips the combine_* fields through edit + save', () => {
    openEditor()

    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({
          combine_enabled: true,
          combine_format: 'srt',
          combine_languages: ['de', 'en'],
          combine_position: { primary: 'top', secondary: 'bottom' },
        }),
      }),
      expect.anything(),
    )
  })

  it('sends combine_enabled=false when the toggle is switched off', () => {
    openEditor()

    // The combine toggle is the only checkbox in the form.
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByText('language_profiles.save'))

    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        data: expect.objectContaining({ combine_enabled: false }),
      }),
      expect.anything(),
    )
  })
})
