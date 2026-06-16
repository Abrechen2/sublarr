import { useCallback, useState } from 'react'

export const DISMISSED_VERSION_KEY = 'sublarr.update-banner.dismissed'

function readDismissed(): string | null {
  try {
    return window.localStorage.getItem(DISMISSED_VERSION_KEY)
  } catch {
    return null
  }
}

/**
 * Tracks which update version the user has dismissed. Persists to
 * localStorage so the dismissal survives reloads, but only for that exact
 * version — a higher future release will differ and re-show the banner.
 * Degrades to in-memory (session) state if localStorage is unavailable.
 */
export function useDismissedVersion() {
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(readDismissed)

  const dismiss = useCallback((version: string) => {
    setDismissedVersion(version)
    try {
      window.localStorage.setItem(DISMISSED_VERSION_KEY, version)
    } catch {
      // localStorage blocked (private mode) — session-only dismissal.
    }
  }, [])

  return { dismissedVersion, dismiss }
}
