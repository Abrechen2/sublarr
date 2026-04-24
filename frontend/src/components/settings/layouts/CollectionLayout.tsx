import type { ReactNode } from 'react'

/**
 * CollectionLayout — Settings Template A (Master-Detail).
 *
 * Use for pages that show a LIST of objects where the user picks one at a
 * time to edit. Examples: Providers, Connections (Sonarr/Radarr/MediaServer
 * instances), Notification Channels, Scheduler Jobs, Plugins, Hooks,
 * Profiles, Prompt Presets, Post-Processing Pipeline steps.
 *
 * NOT for: bounded categorical settings (use FormLayout) or inheritance
 * pages (use RulesLayout).
 *
 * Reference mockup: mockups/settings-templates-concept.html (§ Template A).
 */

export interface CollectionLayoutProps<T> {
  readonly items: readonly T[]
  readonly selectedId: string | null
  readonly getItemId: (item: T) => string
  readonly renderListItem: (item: T, isActive: boolean) => ReactNode
  readonly renderDetail: (item: T | null) => ReactNode
  readonly onSelect: (id: string) => void
  readonly listTitle?: string
  readonly onAdd?: () => void
  readonly addLabel?: string
  readonly emptyState?: ReactNode
  readonly healthRail?: ReactNode
  readonly listWidth?: number
  readonly railWidth?: number
}

const DEFAULT_LIST_WIDTH = 260
const DEFAULT_RAIL_WIDTH = 240

export function CollectionLayout<T>({
  items,
  selectedId,
  getItemId,
  renderListItem,
  renderDetail,
  onSelect,
  listTitle,
  onAdd,
  addLabel = '+ Add',
  emptyState,
  healthRail,
  listWidth = DEFAULT_LIST_WIDTH,
  railWidth = DEFAULT_RAIL_WIDTH,
}: CollectionLayoutProps<T>) {
  const selected = items.find((it) => getItemId(it) === selectedId) ?? null
  const hasRail = Boolean(healthRail)

  const gridTemplate = hasRail
    ? `${listWidth}px 1fr ${railWidth}px`
    : `${listWidth}px 1fr`

  return (
    <div
      data-testid="collection-layout"
      className="grid bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg overflow-hidden"
      style={{ gridTemplateColumns: gridTemplate, minHeight: '520px' }}
    >
      {/* Master list */}
      <aside
        data-testid="collection-list"
        className="border-r border-[var(--border)] p-3 flex flex-col gap-1 overflow-y-auto"
      >
        {(listTitle || onAdd) && (
          <div className="flex items-center justify-between px-2 pt-1 pb-2">
            {listTitle && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-muted">
                {listTitle}
              </span>
            )}
            {onAdd && (
              <button
                type="button"
                onClick={onAdd}
                data-testid="collection-add"
                className="text-[11px] text-[var(--accent)] hover:text-[var(--accent-dim)]"
              >
                {addLabel}
              </button>
            )}
          </div>
        )}

        {items.length === 0
          ? emptyState ?? (
              <div className="text-[11px] text-muted px-3 py-2">No items yet.</div>
            )
          : items.map((item) => {
              const id = getItemId(item)
              const isActive = id === selectedId
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => onSelect(id)}
                  data-testid="collection-item"
                  data-active={isActive ? 'true' : 'false'}
                  className={`text-left rounded px-2 py-1 ${
                    isActive
                      ? 'bg-[var(--accent-bg)] border border-[var(--accent-dim)]'
                      : 'border border-transparent hover:bg-[var(--bg-elevated)]'
                  }`}
                >
                  {renderListItem(item, isActive)}
                </button>
              )
            })}
      </aside>

      {/* Detail editor */}
      <section
        data-testid="collection-detail"
        className="p-6 overflow-y-auto"
      >
        {renderDetail(selected)}
      </section>

      {/* Optional health rail */}
      {hasRail && (
        <aside
          data-testid="collection-rail"
          className="border-l border-[var(--border)] p-4 overflow-y-auto"
        >
          {healthRail}
        </aside>
      )}
    </div>
  )
}
