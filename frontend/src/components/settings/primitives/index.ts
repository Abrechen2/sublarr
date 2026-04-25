/**
 * Shared primitives for the three Settings layout templates.
 *
 * These are cross-cutting UI patterns that Codex called out as
 * non-negotiable in any mature Settings UI for a tool like Sublarr:
 *
 *   InheritanceRow — "inherited from X / overridden here / effective: Y"
 *   BudgetBar      — live quota with remaining / reset / hard-stop pills
 *   ApiKeyField    — masked input + Test-Connection + scope detection
 *   HealthRail     — right-edge checklist with Fix → deep-links
 *
 * Every new Settings page must use these primitives where the concept
 * applies — no ad-hoc reimplementations.
 */

export { InheritanceRow } from './InheritanceRow'
export type { InheritanceRowProps, InheritanceSource } from './InheritanceRow'

export { BudgetBar } from './BudgetBar'
export type { BudgetBarProps } from './BudgetBar'

export { ApiKeyField } from './ApiKeyField'
export type { ApiKeyFieldProps, ApiKeyTestResult } from './ApiKeyField'

export { HealthRail } from './HealthRail'
export type { HealthRailProps, HealthItem, HealthSeverity } from './HealthRail'

export { ConnectionTest } from './ConnectionTest'
export type {
  ConnectionTestProps,
  ConnectionTestResult,
  ConnectionTestState,
} from './ConnectionTest'

export { TriStateToggle } from './TriStateToggle'
export type { TriStateToggleProps } from './TriStateToggle'
