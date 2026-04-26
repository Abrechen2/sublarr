/**
 * URL helpers for cross-page navigation. Keep all URL-shape knowledge here so
 * a future Settings restructuring only touches this file.
 */

export const SETTINGS_PROFILES_PATH = '/settings/profiles'

export type ProfilesScope =
  | { type: 'global' }
  | { type: 'profile'; id: number }
  | { type: 'series'; id: number }
  | { type: 'movie'; id: number }

export function profilesScopeUrl(scope: ProfilesScope, opts?: { from?: string }): string {
  const params = new URLSearchParams()
  if (scope.type === 'global') {
    params.set('scope', 'global')
  } else {
    params.set('scope', `${scope.type}:${scope.id}`)
  }
  if (opts?.from) params.set('from', opts.from)
  return `${SETTINGS_PROFILES_PATH}?${params.toString()}`
}

export function seriesDetailUrl(seriesId: number): string {
  return `/library/series/${seriesId}`
}

export function movieDetailUrl(movieId: number): string {
  return `/movies/${movieId}`
}
