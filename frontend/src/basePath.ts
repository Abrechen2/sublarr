/**
 * The path prefix Sublarr is served under, e.g. "/sublarr".
 *
 * The value cannot be baked in at build time: it is a setting the user changes
 * at runtime, and the same image has to work at "/" and under a prefix. The
 * backend therefore writes it into index.html when it serves the shell, and
 * everything that builds a URL reads it from here — the axios base, the router
 * basename, the service-worker registration.
 *
 * Returned without a trailing slash so callers can concatenate; "" means the
 * app is served at the root, which is the default and by far the common case.
 */
declare global {
  interface Window {
    __SUBLARR_BASE__?: string
  }
}

/**
 * A path prefix is one or more segments of unreserved URL characters. The
 * backend enforces the same shape before it renders the value, and keeps it
 * here too so the two normalizers cannot drift apart — a value that is not a
 * prefix means "serve at the root" rather than something to work around.
 */
const SAFE_PREFIX = /^(\/[A-Za-z0-9._~-]+)+$/

/** Trim whitespace and slashes into the one shape the rest of the app expects. */
export function normalizeBasePath(raw: string | undefined | null): string {
  const value = (raw ?? '').trim()
  if (!value || value === '/') return ''
  // A user typing "sublarr", "/sublarr" or "/sublarr/" all mean the same thing.
  const withLeading = value.startsWith('/') ? value : `/${value}`
  const trimmed = withLeading.replace(/\/+$/, '')
  return SAFE_PREFIX.test(trimmed) ? trimmed : ''
}

export const basePath = normalizeBasePath(
  typeof window === 'undefined' ? '' : window.__SUBLARR_BASE__,
)

/** Prefix an app-absolute path, e.g. withBase("/sw.js") -> "/sublarr/sw.js". */
export function withBase(path: string): string {
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${basePath}${suffix}`
}
