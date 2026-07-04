/** Auto-open the What's-New modal once per version (V1.6 #5). */
import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getHealth } from '@/api/client'
import { versionKey } from '@/content/whatsNew'

const STORAGE_KEY = 'sublarr_whatsnew_seen'

export function useWhatsNew() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    staleTime: 5 * 60_000,
  })

  const key = versionKey(health?.version)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!key) return
    let seen: string | null
    try {
      seen = localStorage.getItem(STORAGE_KEY)
    } catch {
      // localStorage may be unavailable (private mode) — just don't auto-open.
      return
    }
    if (seen !== key) setOpen(true)
  }, [key])

  const markSeen = useCallback(() => {
    if (key) {
      try {
        localStorage.setItem(STORAGE_KEY, key)
      } catch {
        // ignore
      }
    }
  }, [key])

  const dismiss = useCallback(() => {
    markSeen()
    setOpen(false)
  }, [markSeen])

  // Re-openable from System > Status regardless of the seen flag.
  const reopen = useCallback(() => setOpen(true), [])

  return { open, version: key, dismiss, reopen, hasContent: !!key }
}
