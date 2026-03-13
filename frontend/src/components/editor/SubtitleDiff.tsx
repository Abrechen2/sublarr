import { ArrowLeft, Check, CheckSquare, Loader2, SquareX, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { applySubtitleDiff, computeSubtitleDiff } from '../../api/client'
import { useSubtitleBackup } from '../../hooks/useApi'
import type { SubtitleDiffEntry, SubtitleDiffResult } from '../../lib/types'

// ── Types ───────────────────────────────────────────────────────────────────────

interface SubtitleDiffProps {
  filePath: string
  currentContent: string
  format: 'ass' | 'srt'
  onClose?: () => void
  onBackToEditor?: () => void
  onApplied?: () => void
}

const TYPE_BADGE: Record<string, { label: string; color: string }> = {
  unchanged: { label: 'Unchanged', color: 'var(--text-muted)' },
  modified: { label: 'Modified', color: 'var(--warning, #f59e0b)' },
  added: { label: 'Added', color: 'var(--success, #10b981)' },
  removed: { label: 'Removed', color: 'var(--error, #ef4444)' },
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = (seconds % 60).toFixed(2).padStart(5, '0')
  return `${String(h).padStart(1, '0')}:${String(m).padStart(2, '0')}:${s}`
}

// ── Main component ──────────────────────────────────────────────────────────────

export default function SubtitleDiff({
  filePath,
  currentContent,
  format,
  onClose,
  onBackToEditor,
  onApplied,
}: SubtitleDiffProps) {
  const { data: backup, isLoading: backupLoading } = useSubtitleBackup(filePath)

  const [diffResult, setDiffResult] = useState<SubtitleDiffResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)

  const [accepted, setAccepted] = useState<Set<number>>(new Set())
  const [showUnchanged, setShowUnchanged] = useState(false)

  const [applying, setApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)

  // Compute diff when backup and current content are available
  useEffect(() => {
    const backupContent = backup?.content
    if (!backupContent || !currentContent) return

    let cancelled = false
    setLoading(true)
    setDiffError(null)

    computeSubtitleDiff(backupContent, currentContent)
      .then(result => {
        if (cancelled) return
        setDiffResult(result)
        // Pre-accept all changed entries
        const changedIndices = result.diffs
          .map((d, i) => ({ type: d.type, i }))
          .filter(({ type }) => type !== 'unchanged')
          .map(({ i }) => i)
        setAccepted(new Set(changedIndices))
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDiffError(err instanceof Error ? err.message : 'Failed to compute diff')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [backup?.content, currentContent])

  const toggleAccepted = (index: number) => {
    setAccepted(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  const acceptAll = () => {
    if (!diffResult) return
    const all = diffResult.diffs
      .map((d, i) => ({ type: d.type, i }))
      .filter(({ type }) => type !== 'unchanged')
      .map(({ i }) => i)
    setAccepted(new Set(all))
  }

  const rejectAll = () => {
    setAccepted(new Set())
  }

  const handleApply = async () => {
    if (!diffResult || !backup?.content) return
    const rejectedIndices = diffResult.diffs
      .map((_, i) => i)
      .filter(i => !accepted.has(i) && diffResult.diffs[i].type !== 'unchanged')

    setApplying(true)
    setApplyError(null)
    try {
      await applySubtitleDiff(filePath, backup.content, currentContent, rejectedIndices)
      onApplied?.()
    } catch (err: unknown) {
      setApplyError(err instanceof Error ? err.message : 'Failed to apply changes')
    } finally {
      setApplying(false)
    }
  }

  // ── Loading / error states ─────────────────────────────────────────────────

  if (backupLoading) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-muted)' }}>
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading backup...
        </div>
      </div>
    )
  }

  if (!backup?.content) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 flex-col items-center justify-center gap-2" style={{ color: 'var(--text-muted)' }}>
          <span className="text-sm">No backup found for this file.</span>
          <span className="text-xs">Save the file first to create a backup.</span>
        </div>
      </div>
    )
  }

  if (diffError) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3" style={{ color: 'var(--error, #ef4444)' }}>
          <span className="text-sm">{diffError}</span>
          <button
            onClick={() => {
              setDiffError(null)
              setDiffResult(null)
            }}
            className="rounded px-4 py-1.5 text-sm transition-colors"
            style={{ backgroundColor: 'var(--bg-surface-hover)', color: 'var(--text-primary)' }}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // ── Main diff table ─────────────────────────────────────────────────────────

  const visibleDiffs = diffResult
    ? diffResult.diffs
        .map((d, i) => ({ ...d, index: i }))
        .filter(d => showUnchanged || d.type !== 'unchanged')
    : []

  const changedCount = diffResult?.changed ?? 0
  const acceptedCount = accepted.size

  return (
    <div className="flex h-full flex-col">
      <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />

      {/* Toolbar */}
      <div
        className="flex items-center gap-2 px-4 py-2 flex-shrink-0 flex-wrap"
        style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        {diffResult && (
          <>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {changedCount} change{changedCount !== 1 ? 's' : ''} —{' '}
              {acceptedCount} accepted
            </span>

            <div className="flex gap-1 ml-2">
              <button
                onClick={acceptAll}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--success)', border: '1px solid var(--border)' }}
                title="Accept all changes"
              >
                <CheckSquare size={12} />
                Accept All
              </button>
              <button
                onClick={rejectAll}
                className="flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors"
                style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--error)', border: '1px solid var(--border)' }}
                title="Reject all changes"
              >
                <SquareX size={12} />
                Reject All
              </button>
            </div>

            <label className="ml-2 flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={showUnchanged}
                onChange={e => setShowUnchanged(e.target.checked)}
                className="rounded"
              />
              Show unchanged
            </label>

            <div className="flex-1" />

            <button
              onClick={() => void handleApply()}
              disabled={applying || changedCount === 0}
              className="flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)', color: 'white' }}
            >
              {applying ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
              Apply Changes
            </button>
          </>
        )}
      </div>

      {/* Apply error banner */}
      {applyError && (
        <div
          className="px-4 py-2 text-sm flex-shrink-0"
          style={{ backgroundColor: 'var(--error-bg)', color: 'var(--error)', borderBottom: '1px solid var(--border)' }}
        >
          {applyError}
        </div>
      )}

      {/* Diff loading spinner */}
      {loading && (
        <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-muted)' }}>
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Computing diff...
        </div>
      )}

      {/* Empty state */}
      {!loading && diffResult && changedCount === 0 && (
        <div className="flex flex-1 items-center justify-center text-sm" style={{ color: 'var(--text-muted)' }}>
          No differences found between backup and current content.
        </div>
      )}

      {/* Diff table */}
      {!loading && diffResult && changedCount > 0 && (
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ backgroundColor: 'var(--bg-elevated)', borderBottom: '1px solid var(--border)' }}>
                <th className="px-3 py-2 text-left text-xs font-medium w-10" style={{ color: 'var(--text-muted)' }}>#</th>
                <th className="px-3 py-2 text-left text-xs font-medium w-28" style={{ color: 'var(--text-muted)' }}>Time</th>
                <th className="px-3 py-2 text-left text-xs font-medium w-20" style={{ color: 'var(--text-muted)' }}>Type</th>
                <th className="px-3 py-2 text-left text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Original</th>
                <th className="px-3 py-2 text-left text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Modified</th>
                <th className="px-3 py-2 text-center text-xs font-medium w-20" style={{ color: 'var(--text-muted)' }}>Accept</th>
              </tr>
            </thead>
            <tbody>
              {visibleDiffs.map(entry => (
                <DiffRow
                  key={entry.index}
                  entry={entry}
                  entryIndex={entry.index}
                  accepted={accepted.has(entry.index)}
                  onToggle={toggleAccepted}
                  format={format}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

interface DiffRowProps {
  entry: SubtitleDiffEntry & { index: number }
  entryIndex: number
  accepted: boolean
  onToggle: (index: number) => void
  format: 'ass' | 'srt'
}

function DiffRow({ entry, entryIndex, accepted, onToggle, format: _format }: DiffRowProps) {
  const isChangeable = entry.type !== 'unchanged'
  const badge = TYPE_BADGE[entry.type]
  const timeCue = entry.original ?? entry.modified

  const rowBg = !isChangeable
    ? 'transparent'
    : accepted
    ? 'rgba(var(--success-rgb, 16, 185, 129), 0.07)'
    : 'rgba(var(--error-rgb, 239, 68, 68), 0.07)'

  return (
    <tr
      style={{
        backgroundColor: rowBg,
        borderBottom: '1px solid var(--border)',
        opacity: !isChangeable ? 0.5 : 1,
      }}
    >
      {/* Index */}
      <td className="px-3 py-2 text-xs" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
        {entryIndex}
      </td>

      {/* Time range */}
      <td className="px-3 py-2 text-xs whitespace-nowrap" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
        {timeCue ? `${formatTime(timeCue.start)} → ${formatTime(timeCue.end)}` : '—'}
      </td>

      {/* Type badge */}
      <td className="px-3 py-2">
        <span className="text-xs font-medium" style={{ color: badge.color }}>
          {badge.label}
        </span>
      </td>

      {/* Original text */}
      <td className="px-3 py-2 text-xs align-top" style={{ color: 'var(--text-primary)' }}>
        {entry.original?.text ?? <span style={{ color: 'var(--text-muted)' }}>—</span>}
      </td>

      {/* Modified text */}
      <td className="px-3 py-2 text-xs align-top" style={{ color: 'var(--text-primary)' }}>
        {entry.modified?.text ?? <span style={{ color: 'var(--text-muted)' }}>—</span>}
      </td>

      {/* Accept/reject toggle */}
      <td className="px-3 py-2 text-center">
        {isChangeable ? (
          <button
            onClick={() => onToggle(entryIndex)}
            className="rounded p-1 transition-colors"
            style={{
              color: accepted ? 'var(--success)' : 'var(--error)',
              backgroundColor: accepted ? 'rgba(var(--success-rgb, 16, 185, 129), 0.12)' : 'rgba(var(--error-rgb, 239, 68, 68), 0.12)',
            }}
            title={accepted ? 'Click to reject' : 'Click to accept'}
          >
            {accepted ? <Check size={14} /> : <X size={14} />}
          </button>
        ) : null}
      </td>
    </tr>
  )
}

/** Shared header bar for all diff states */
function DiffHeader({
  onClose,
  onBackToEditor,
}: {
  onClose?: () => void
  onBackToEditor?: () => void
}) {
  return (
    <div
      className="flex items-center gap-2 px-3 py-1.5 flex-shrink-0"
      style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>Diff View</span>

      <div className="flex-1" />

      {onBackToEditor && (
        <button
          onClick={onBackToEditor}
          className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm transition-colors"
          style={{ color: 'var(--text-secondary)' }}
          title="Back to editor"
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Editor
        </button>
      )}

      {onClose && (
        <button
          onClick={onClose}
          className="rounded p-1.5 transition-colors"
          style={{ color: 'var(--text-muted)' }}
          title="Close"
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
