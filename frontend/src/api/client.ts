/**
 * Public API surface for the Sublarr frontend.
 * Re-exports everything from domain-specific API modules.
 *
 * Import paths throughout the codebase continue to use '@/api/client' or
 * '../api/client' — this file ensures full backwards compatibility.
 */

export { api, bootstrapApiKey } from './core'
export * from './health'
export * from './library'
export * from './wanted'
export * from './translation'
export * from './providers'
export * from './settings'
export * from './system'

export default (await import('./core')).api
