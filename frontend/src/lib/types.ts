/** Re-exports from domain-specific type files. This file exists for backwards compatibility. */

export * from '../types/core'
export * from '../types/library'
export * from '../types/wanted'
export * from '../types/translation'
export * from '../types/providers'
export * from '../types/settings'
export * from '../types/system'
export * from '../types/subtitleHealth'

// `HealthIssue` and `HealthFixResult` exist in BOTH ../types/system (legacy
// per-file health check) and ../types/subtitleHealth (the Subtitle Health
// subsystem). Re-exporting both via `export *` is ambiguous (TS2308), so the
// barrel explicitly exposes the legacy `system` ones for backwards
// compatibility (the only remaining barrel consumer is HealthCheckPanel).
// Subtitle-Health code must import these from '@/types/subtitleHealth' directly.
export type { HealthIssue, HealthFixResult } from '../types/system'
