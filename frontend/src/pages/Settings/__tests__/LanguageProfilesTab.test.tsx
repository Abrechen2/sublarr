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
