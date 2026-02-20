/**
 * ScanProgressIndicator -- Floating live scan progress overlay.
 *
 * Listens to `wanted_scan_progress` WebSocket events and shows a compact
 * card (bottom-right) while a wanted scan is running. Fades out after
 * the scan completes.
 */
import { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Loader2, CheckCircle2 } from 'lucide-react'

interface ScanProgress {
  current: number
  total: number
  phase: string
  added: number
  updated: number
}

export function ScanProgressIndicator() {
  const [progress, setProgress] = useState<ScanProgress | null>(null)
  const [done, setDone] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useWebSocket({
    onWantedScanProgress: (data) => {
      const d = data as ScanProgress
      setProgress(d)
      setDone(false)
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    },
    onWantedScanCompleted: () => {
      setDone(true)
      hideTimerRef.current = setTimeout(() => {
        setProgress(null)
        setDone(false)
      }, 3000)
    },
  })

  useEffect(() => {
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    }
  }, [])

  if (!progress) return null

  const pct = progress.total > 0 ? Math.round((progress.current / progress.total) * 100) : 0

  return (
    <div
      className="fixed bottom-20 right-4 z-50 w-56 rounded-xl shadow-lg border transition-opacity duration-500"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderColor: 'var(--border)',
        opacity: done ? 0.7 : 1,
      }}
    >
      <div className="p-3">
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          {done ? (
            <CheckCircle2 size={14} style={{ color: 'var(--success)', flexShrink: 0 }} />
          ) : (
            <Loader2 size={14} className="animate-spin" style={{ color: 'var(--accent)', flexShrink: 0 }} />
          )}
          <span className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
            {done ? 'Scan complete' : 'Scanning…'}
          </span>
          <span className="text-xs ml-auto font-mono tabular-nums" style={{ color: 'var(--text-muted)' }}>
            {pct}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="h-1.5 rounded-full overflow-hidden mb-2" style={{ backgroundColor: 'var(--bg-primary)' }}>
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${pct}%`, backgroundColor: done ? 'var(--success)' : 'var(--accent)' }}
          />
        </div>

        {/* Phase + counter */}
        <div className="flex justify-between items-center">
          <span className="text-[10px] truncate" style={{ color: 'var(--text-muted)', maxWidth: '65%' }}>
            {progress.phase}
          </span>
          <span className="text-[10px] font-mono tabular-nums" style={{ color: 'var(--text-secondary)' }}>
            {progress.current}/{progress.total}
          </span>
        </div>

        {/* Added/Updated stats */}
        {(progress.added > 0 || progress.updated > 0) && (
          <div className="flex gap-3 mt-1.5">
            {progress.added > 0 && (
              <span className="text-[10px]" style={{ color: 'var(--success)' }}>
                +{progress.added} added
              </span>
            )}
            {progress.updated > 0 && (
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                ~{progress.updated} updated
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
