/**
 * Show the HI-removal data-loss notice exactly once.
 *
 * Not version-gated like What's-New: the damage predates this release, so the
 * notice must reach every existing install regardless of which version they
 * upgrade from. A single acknowledgement id, remembered locally.
 */
import { useState, useEffect, useCallback } from 'react'

const NOTICE_ID = 'hi-interjection-data-loss-2026-07'
const STORAGE_KEY = 'sublarr_notice_ack'

export function useSubtitleDamageNotice() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) !== NOTICE_ID) setOpen(true)
    } catch {
      // localStorage unavailable (private mode) — don't nag on every render.
    }
  }, [])

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, NOTICE_ID)
    } catch {
      // ignore
    }
    setOpen(false)
  }, [])

  return { open, dismiss }
}
