import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RulesLayout } from '@/components/settings/layouts'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import {
  useScopesTree,
  useResolved,
  useOverrideMutation,
  useResetMutation,
  useDeleteOverride,
} from './profilesOverrides/useProfilesOverrides'
import { ScopeTree, type ScopeRef, type ProfileAction } from './profilesOverrides/ScopeTree'
import { ScopeDetail } from './profilesOverrides/ScopeDetail'
import { ProfileEditDialog, type ProfileDialogMode } from './profilesOverrides/ProfileEditDialog'
import {
  createLanguageProfile,
  updateLanguageProfile,
  deleteLanguageProfile,
  setProfileAsDefaultForAll,
} from '@/api/settings'
import { SETTINGS_PROFILES_PATH } from '@/lib/routes'

// ─── URL helpers ──────────────────────────────────────────────────────────────

function parseScopeFromUrl(param: string | null): ScopeRef {
  if (!param || param === 'global') return { type: 'global' }
  const [type, idStr] = param.split(':')
  const id = Number(idStr)
  if (!Number.isFinite(id)) return { type: 'global' }
  if (type === 'profile') return { type: 'profile', id }
  if (type === 'series') return { type: 'series', id }
  if (type === 'movie') return { type: 'movie', id }
  return { type: 'global' }
}

function scopeToUrlValue(scope: ScopeRef): string {
  if (scope.type === 'global') return 'global'
  return `${scope.type}:${scope.id}`
}

// ─── Dialog state type ───────────────────────────────────────────────────────

type DialogState =
  | { mode: 'add' }
  | { mode: 'edit'; id: number; name: string }
  | { mode: 'delete'; id: number; name: string; impact: { series_count: number; movies_count: number } }

// ─── Page ────────────────────────────────────────────────────────────────────

export function ProfilesOverridesPage() {
  const { t } = useTranslation('settings')
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selected = useMemo(() => parseScopeFromUrl(searchParams.get('scope')), [searchParams])
  const fromParam = searchParams.get('from') ?? undefined

  const [dialog, setDialog] = useState<DialogState | null>(null)

  const { data: tree, isLoading: treeLoading } = useScopesTree()
  const { data: resolved } = useResolved(
    selected.type,
    selected.type === 'global' ? null : selected.id,
  )

  // Mutations are only valid for series/movie scopes; -1 is a safe placeholder
  // for global/profile selections — those scopes are never writable.
  const overrideMut = useOverrideMutation(
    selected.type === 'series' ? 'series' : 'movie',
    selected.type === 'series' || selected.type === 'movie' ? selected.id : -1,
  )
  const resetMut = useResetMutation(
    selected.type === 'series' ? 'series' : 'movie',
    selected.type === 'series' || selected.type === 'movie' ? selected.id : -1,
  )
  const deleteMut = useDeleteOverride(
    selected.type === 'series' ? 'series' : 'movie',
  )

  // Focus detail panel on scope change for screen-reader announcement
  const detailHeaderRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (resolved) detailHeaderRef.current?.focus()
  }, [resolved?.scope.type, (resolved?.scope as { id?: number })?.id])

  const handleSelect = (scope: ScopeRef) => {
    const next = new URLSearchParams(searchParams)
    next.set('scope', scopeToUrlValue(scope))
    // Clear from param when manually selecting a scope
    next.delete('from')
    setSearchParams(next, { replace: true })
  }

  const handleProfileAction = (action: ProfileAction) => {
    if (action.kind === 'add') {
      setDialog({ mode: 'add' })
    } else if (action.kind === 'edit') {
      const p = tree?.profiles.find((pr) => pr.id === action.id)
      if (p) setDialog({ mode: 'edit', id: p.id, name: p.name })
    } else if (action.kind === 'delete') {
      const p = tree?.profiles.find((pr) => pr.id === action.id)
      if (p) {
        setDialog({
          mode: 'delete',
          id: p.id,
          name: p.name,
          impact: { series_count: p.series.length, movies_count: p.movies.length },
        })
      }
    } else if (action.kind === 'set-default') {
      void setProfileAsDefaultForAll(action.id)
    }
  }

  const handleProfileSubmit = async (payload: { id?: number; name: string }) => {
    if (dialog?.mode === 'add') {
      await createLanguageProfile({
        name: payload.name,
        target_languages: ['de'],
        target_language_names: ['German'],
      })
    } else if (dialog?.mode === 'edit') {
      await updateLanguageProfile(dialog.id, { name: payload.name })
    } else if (dialog?.mode === 'delete') {
      await deleteLanguageProfile(dialog.id)
    }
  }

  const handleOverride = (fieldKey: string, value: unknown) => {
    overrideMut.mutate({ [fieldKey]: value })
  }

  const handleRemove = () => {
    if (selected.type !== 'series' && selected.type !== 'movie') return
    deleteMut.mutate(selected.id, {
      onSuccess: () => {
        navigate(fromParam ?? SETTINGS_PROFILES_PATH, { replace: true })
      },
    })
  }

  // Empty state: tree loaded but no series/movies have explicit overrides
  const treeEmpty =
    tree &&
    tree.profiles.every((p) => !p.series.length && !p.movies.length) &&
    !tree.unassigned_series.length &&
    !tree.unassigned_movies.length

  const showEmptyState = treeEmpty && (selected.type === 'global' || selected.type === 'profile')

  return (
    <SettingsDetailLayout
      title={t('profiles_overrides.title', 'Profiles & Overrides')}
      subtitle={t(
        'profiles_overrides.subtitle',
        'Browse and override the Global → Profile → Series/Movie inheritance chain.',
      )}
    >
      <RulesLayout
        scopeTree={
          treeLoading || !tree ? (
            <div className="text-xs text-muted">Loading…</div>
          ) : (
            <ScopeTree
              tree={tree}
              selected={selected}
              onSelect={handleSelect}
              onProfileAction={handleProfileAction}
            />
          )
        }
        resolvedHeader={
          <div ref={detailHeaderRef} tabIndex={-1} aria-live="polite">
            {!resolved && (
              <div className="text-xs text-muted">Select a scope from the tree.</div>
            )}
          </div>
        }
        overrideWidget={
          showEmptyState ? (
            <div
              data-testid="profiles-overrides-empty-state"
              className="flex flex-col gap-2 p-4 rounded bg-[var(--bg-elevated)] border border-[var(--border)] text-center"
            >
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t('profiles_overrides.empty_state.title', 'No overrides yet')}
              </p>
              <p className="text-xs text-[var(--text-muted)]">
                {t(
                  'profiles_overrides.empty_state.body',
                  'Open a series in the library and click "Subtitle settings" to create your first override.',
                )}
              </p>
            </div>
          ) : resolved ? (
            <ScopeDetail
              resolved={resolved}
              onChange={handleOverride}
              onReset={() => resetMut.mutate()}
              onRemove={
                (selected.type === 'series' || selected.type === 'movie')
                  ? handleRemove
                  : undefined
              }
              backHref={
                (selected.type === 'series' || selected.type === 'movie') && fromParam
                  ? fromParam
                  : undefined
              }
            />
          ) : (
            <div />
          )
        }
      />

      {dialog && (
        <ProfileEditDialog
          mode={dialog.mode as ProfileDialogMode}
          initialId={dialog.mode !== 'add' ? dialog.id : undefined}
          initialName={dialog.mode !== 'add' ? dialog.name : undefined}
          impact={dialog.mode === 'delete' ? dialog.impact : undefined}
          onClose={() => setDialog(null)}
          onSubmit={handleProfileSubmit}
        />
      )}
    </SettingsDetailLayout>
  )
}
