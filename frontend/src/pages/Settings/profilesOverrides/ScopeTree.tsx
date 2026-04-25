import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Plus, MoreHorizontal, Star } from 'lucide-react'
import type { ScopesTree } from '@/api/profilesOverrides'

export type ScopeRef =
  | { type: 'global' }
  | { type: 'profile'; id: number }
  | { type: 'series'; id: number }
  | { type: 'movie'; id: number }

export type ProfileAction =
  | { kind: 'add' }
  | { kind: 'edit'; id: number }
  | { kind: 'delete'; id: number }
  | { kind: 'set-default'; id: number }

export interface ScopeTreeProps {
  readonly tree: ScopesTree
  readonly selected: ScopeRef | null
  readonly onSelect: (scope: ScopeRef) => void
  readonly onProfileAction: (action: ProfileAction) => void
}

function isSelected(a: ScopeRef | null, b: ScopeRef): boolean {
  if (!a || a.type !== b.type) return false
  if (a.type === 'global' || b.type === 'global') return a.type === b.type
  return (a as { id: number }).id === (b as { id: number }).id
}

export function ScopeTree({ tree, selected, onSelect, onProfileAction }: ScopeTreeProps) {
  const { t } = useTranslation('settings')
  const [expanded, setExpanded] = useState<Set<number>>(
    new Set(tree.profiles.map((p) => p.id)),
  )
  const [openMenu, setOpenMenu] = useState<number | null>(null)

  const toggle = (id: number) =>
    setExpanded((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const itemClass = (s: ScopeRef) =>
    isSelected(selected, s)
      ? 'flex items-center gap-1.5 px-2 py-1 rounded text-xs bg-[var(--accent-bg)] text-[var(--accent)] cursor-pointer'
      : 'flex items-center gap-1.5 px-2 py-1 rounded text-xs cursor-pointer hover:bg-[var(--bg-elevated)]'

  return (
    <div role="tree" aria-label="Scope tree" className="text-[12px]">
      {/* Global */}
      <div
        role="treeitem"
        aria-selected={selected?.type === 'global'}
        className={itemClass({ type: 'global' })}
        onClick={() => onSelect({ type: 'global' })}
      >
        <span className="text-[var(--accent)]">◉</span>
        {t('profiles_overrides.scope.global', 'Global default')}
      </div>

      {/* Profiles */}
      {tree.profiles.map((p) => {
        const isOpen = expanded.has(p.id)
        return (
          <div key={p.id} role="treeitem" aria-expanded={isOpen}>
            <div className="flex items-center gap-1 group">
              <button
                type="button"
                onClick={() => toggle(p.id)}
                aria-label={isOpen ? 'collapse' : 'expand'}
                className="text-[var(--text-muted)]"
              >
                {isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
              </button>
              <div
                className={itemClass({ type: 'profile', id: p.id }) + ' flex-1'}
                onClick={() => onSelect({ type: 'profile', id: p.id })}
              >
                <span className="text-[var(--text-muted)]">◐</span>
                <span className="flex-1 truncate">{p.name}</span>
                {p.is_default && <Star size={10} className="text-[var(--warning)]" />}
              </div>
              <button
                type="button"
                className="opacity-0 group-hover:opacity-100 p-1 text-[var(--text-muted)] hover:text-[var(--accent)]"
                onClick={() => setOpenMenu(openMenu === p.id ? null : p.id)}
                aria-label="profile actions"
              >
                <MoreHorizontal size={11} />
              </button>
              {openMenu === p.id && (
                <div
                  role="menu"
                  className="absolute right-2 mt-6 z-10 bg-[var(--bg-elevated)] border border-[var(--border)] rounded shadow-lg"
                >
                  <button
                    onClick={() => {
                      onProfileAction({ kind: 'edit', id: p.id })
                      setOpenMenu(null)
                    }}
                    className="block w-full text-left px-3 py-1.5 text-[11px] hover:bg-[var(--accent-bg)]"
                  >
                    {t('profiles_overrides.menu.edit', 'Edit')}
                  </button>
                  {!p.is_default && (
                    <button
                      onClick={() => {
                        onProfileAction({ kind: 'set-default', id: p.id })
                        setOpenMenu(null)
                      }}
                      className="block w-full text-left px-3 py-1.5 text-[11px] hover:bg-[var(--accent-bg)]"
                    >
                      {t('profiles_overrides.menu.set_default', 'Set as default')}
                    </button>
                  )}
                  <button
                    onClick={() => {
                      onProfileAction({ kind: 'delete', id: p.id })
                      setOpenMenu(null)
                    }}
                    className="block w-full text-left px-3 py-1.5 text-[11px] text-[var(--error)] hover:bg-[var(--accent-bg)]"
                  >
                    {t('profiles_overrides.menu.delete', 'Delete')}
                  </button>
                </div>
              )}
            </div>
            {isOpen && (
              <div className="ml-4">
                {p.series.map((s) => (
                  <div
                    key={`series-${s.id}`}
                    role="treeitem"
                    className={itemClass({ type: 'series', id: s.id })}
                    onClick={() => onSelect({ type: 'series', id: s.id })}
                  >
                    <span className="text-[var(--text-muted)]">▦</span>
                    <span className="truncate">{s.title}</span>
                  </div>
                ))}
                {p.movies.map((m) => (
                  <div
                    key={`movie-${m.id}`}
                    role="treeitem"
                    className={itemClass({ type: 'movie', id: m.id })}
                    onClick={() => onSelect({ type: 'movie', id: m.id })}
                  >
                    <span className="text-[var(--text-muted)]">◎</span>
                    <span className="truncate">{m.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      {/* Unassigned series */}
      {tree.unassigned_series.length > 0 && (
        <>
          <div className="text-[10px] text-[var(--text-muted)] mt-2 px-2 uppercase tracking-wider">
            {t('profiles_overrides.section.series_no_profile', 'Series (no profile)')}
          </div>
          {tree.unassigned_series.map((s) => (
            <div
              key={`u-series-${s.id}`}
              role="treeitem"
              className={itemClass({ type: 'series', id: s.id })}
              onClick={() => onSelect({ type: 'series', id: s.id })}
            >
              <span className="text-[var(--text-muted)]">▦</span>
              <span className="truncate">{s.title}</span>
            </div>
          ))}
        </>
      )}

      {/* Unassigned movies */}
      {tree.unassigned_movies.length > 0 && (
        <>
          <div className="text-[10px] text-[var(--text-muted)] mt-2 px-2 uppercase tracking-wider">
            {t('profiles_overrides.section.movies_no_profile', 'Movies (no profile)')}
          </div>
          {tree.unassigned_movies.map((m) => (
            <div
              key={`u-movie-${m.id}`}
              role="treeitem"
              className={itemClass({ type: 'movie', id: m.id })}
              onClick={() => onSelect({ type: 'movie', id: m.id })}
            >
              <span className="text-[var(--text-muted)]">◎</span>
              <span className="truncate">{m.title}</span>
            </div>
          ))}
        </>
      )}

      {/* Add profile button */}
      <button
        type="button"
        onClick={() => onProfileAction({ kind: 'add' })}
        className="mt-3 flex items-center gap-1 px-2 py-1 text-[11px] text-[var(--text-secondary)] border border-[var(--border)] rounded hover:bg-[var(--accent-bg)] hover:text-[var(--accent)]"
      >
        <Plus size={11} />
        {t('profiles_overrides.action.add_profile', 'Add profile')}
      </button>
    </div>
  )
}
