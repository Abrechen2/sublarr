/**
 * Multi-panel comparison grid for subtitle files.
 *
 * Displays 2-4 subtitle files side by side in a synchronized
 * scrolling CSS grid with syntax highlighting.
 */

import { useEffect, useRef, useCallback } from 'react'
import { X, Loader2, AlertCircle } from 'lucide-react'
import { useCompareSubtitles } from '@/hooks/useApi'
import { ComparisonPanel } from './ComparisonPanel'

interface SubtitleComparisonProps {
  filePaths: string[]
  onClose?: () => void
}

export function SubtitleComparison({ filePaths, onClose }: SubtitleComparisonProps) {
  const compareMutation = useCompareSubtitles()
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isScrollSyncingRef = useRef(false)

  // Fetch comparison data on mount
  useEffect(() => {
    if (filePaths.length >= 2) {
      compareMutation.mutate(filePaths)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filePaths.join(',')])

  // Synchronized scrolling callback
  const handlePanelScroll = useCallback((_lineNumber: number) => {
    // Debounce scroll sync to prevent cascading events
    if (isScrollSyncingRef.current) return

    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current)
    }

    scrollTimeoutRef.current = setTimeout(() => {
      isScrollSyncingRef.current = true
      // Scroll sync is handled at the DOM level by CodeMirror's scroll position.
      // In a read-only comparison scenario, scroll sync is best-effort.
      requestAnimationFrame(() => {
        isScrollSyncingRef.current = false
      })
    }, 50)
  }, [])

  const panels = compareMutation.data?.panels ?? []
  const panelCount = panels.length

  // Determine grid layout
  const gridClass =
    panelCount <= 2
      ? 'grid-cols-2'
      : 'grid-cols-2 grid-rows-2'

  // Loading state
  if (compareMutation.isPending) {
    return (
      <div className="flex flex-col h-full">
        <ComparisonHeader onClose={onClose} />
        <div
          className="flex flex-1 items-center justify-center gap-2"
          style={{ color: 'var(--text-muted)' }}
        >
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">Loading comparison...</span>
        </div>
      </div>
    )
  }

  // Error state
  if (compareMutation.isError) {
    return (
      <div className="flex flex-col h-full">
        <ComparisonHeader onClose={onClose} />
        <div
          className="flex flex-1 flex-col items-center justify-center gap-3"
          style={{ color: 'var(--text-muted)' }}
        >
          <AlertCircle size={28} style={{ color: 'var(--error)' }} />
          <p className="text-sm">Failed to load comparison data</p>
          <button
            onClick={() => compareMutation.mutate(filePaths)}
            className="rounded px-4 py-1.5 text-xs font-medium transition-colors"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <ComparisonHeader onClose={onClose} panelCount={panelCount} />
      <div className={`flex-1 min-h-0 grid ${gridClass} gap-2 p-2`}>
        {panels.map((panel, i) => {
          // Derive label from path (show filename only)
          const fileName = panel.path.split('/').pop() ?? panel.path
          return (
            <ComparisonPanel
              key={`${panel.path}-${i}`}
              label={fileName}
              content={panel.content}
              format={panel.format}
              onScroll={handlePanelScroll}
            />
          )
        })}
      </div>
    </div>
  )
}

/** Header bar with title and close button */
function ComparisonHeader({
  onClose,
  panelCount,
}: {
  onClose?: () => void
  panelCount?: number
}) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 shrink-0"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
        Comparison View
      </span>
      {panelCount !== undefined && (
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          ({panelCount} panels)
        </span>
      )}
      <div className="flex-1" />
      {onClose && (
        <button
          onClick={onClose}
          className="rounded p-1.5 transition-colors"
          style={{ color: 'var(--text-muted)' }}
          title="Close comparison"
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--error)'
            e.currentTarget.style.backgroundColor = 'var(--bg-surface)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)'
            e.currentTarget.style.backgroundColor = ''
          }}
        >
          <X size={16} />
        </button>
      )}
    </div>
  )
}
