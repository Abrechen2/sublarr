/**
 * Barrel for the system / settings React Query hooks.
 *
 * The hooks were split out of this single ~850-line file into cohesive
 * domain modules under ./system/. This barrel preserves the historical
 * import surface `@/hooks/useSystemApi` so existing consumers keep working
 * unchanged.
 */
export * from './system/core'
export * from './system/standalone'
export * from './system/maintenance'
export * from './system/search-keys'
export * from './system/notifications'
export * from './system/cleanup'
export * from './system/tools'
