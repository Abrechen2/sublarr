import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RulesLayout } from '@/components/settings/layouts'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import {
  useScopesTree,
  useResolved,
  useOverrideMutation,
  useResetMutation,
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
  const [searchParams, setSearchParams] = useSearchParams()
  const selected = useMemo(() => parseScopeFromUrl(searchParams.get('scope')), [searchParams])

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

  // Focus detail panel on scope change for screen-reader announcement
  const detailHeaderRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (resolved) detailHeaderRef.current?.focus()
  }, [resolved?.scope.type, (resolved?.scope as { id?: number })?.id])

  const handleSelect = (scope: ScopeRef) => {
    const next = new URLSearchParams(searchParams)
    next.set('scope', scopeToUrlValue(scope))
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
          resolved ? (
            <ScopeDetail
              resolved={resolved}
              onChange={handleOverride}
              onReset={() => resetMut.mutate()}
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
