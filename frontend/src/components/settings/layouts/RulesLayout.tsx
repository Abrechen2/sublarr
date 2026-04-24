import type { ReactNode } from 'react'

/**
 * RulesLayout — Settings Template C (Inheritance / Overrides).
 *
 * Use for pages whose primary UX is "understand what wins, what's
 * inherited, where to override" — NOT "edit this object" (CollectionLayout)
 * and NOT "fill this page" (FormLayout).
 *
 * Examples: Profiles & Overrides, per-Series overrides, per-Movie
 * overrides, Quiet-Hours policies.
 *
 * Per Codex blueprint: the scope tree is a CONTROL INSIDE the left pane,
 * NOT a separate template. Nested hierarchies are flattened into the
 * scopeTree slot.
 *
 * Reference mockup: mockups/settings-templates-concept.html (§ Template C).
 */

export interface RulesLayoutProps {
  /** Left pane: scope tree control (Global → Profile → Series …). */
  readonly scopeTree: ReactNode
  /** Top-right: the "resolved value" headline with inheritance chain. */
  readonly resolvedHeader: ReactNode
  /** Center-right: override widgets (Inherit / Force X / Force Y buttons). */
  readonly overrideWidget: ReactNode
  /** Bottom-right: summary of other rules at this scope with inherited/overridden pills. */
  readonly otherRules?: ReactNode
  /** Optional right-edge health rail. Inserts a 3rd column when provided. */
  readonly healthRail?: ReactNode
  /** Breadcrumb trail showing the selected scope path. Caller-rendered. */
  readonly breadcrumb?: ReactNode
  readonly treeWidth?: number
  readonly railWidth?: number
}

const DEFAULT_TREE_WIDTH = 300
const DEFAULT_RAIL_WIDTH = 240

export function RulesLayout({
  scopeTree,
  resolvedHeader,
  overrideWidget,
  otherRules,
  healthRail,
  breadcrumb,
  treeWidth = DEFAULT_TREE_WIDTH,
  railWidth = DEFAULT_RAIL_WIDTH,
}: RulesLayoutProps) {
  const hasRail = Boolean(healthRail)

  const gridTemplate = hasRail
    ? `${treeWidth}px 1fr ${railWidth}px`
    : `${treeWidth}px 1fr`

  return (
    <div data-testid="rules-layout" className="flex flex-col gap-4">
      {breadcrumb && (
        <div data-testid="rules-breadcrumb" className="text-[11px] text-muted">
          {breadcrumb}
        </div>
      )}

      <div
        className="grid bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg overflow-hidden"
        style={{ gridTemplateColumns: gridTemplate, minHeight: '520px' }}
      >
        {/* Left: scope tree */}
        <aside
          data-testid="rules-scope-tree"
          className="border-r border-[var(--border)] p-3 overflow-y-auto"
          aria-label="Scope tree"
        >
          {scopeTree}
        </aside>

        {/* Center: resolved + override + other rules, stacked */}
        <section
          data-testid="rules-detail"
          className="p-6 overflow-y-auto flex flex-col gap-4"
        >
          <div data-testid="rules-resolved">{resolvedHeader}</div>
          <div data-testid="rules-override">{overrideWidget}</div>
          {otherRules && <div data-testid="rules-other">{otherRules}</div>}
        </section>

        {/* Optional right rail */}
        {hasRail && (
          <aside
            data-testid="rules-rail"
            className="border-l border-[var(--border)] p-4 overflow-y-auto"
          >
            {healthRail}
          </aside>
        )}
      </div>
    </div>
  )
}
