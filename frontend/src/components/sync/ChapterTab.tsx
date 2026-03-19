/**
 * Chapter tab — apply a timing offset restricted to a single chapter's time range.
 */

import { Loader2, Check, Eye } from 'lucide-react'
import type { Chapter } from '@/lib/types'

function _formatMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

interface ChapterTabProps {
  chapters: Chapter[]
  selectedChapterId: number | null
  offsetMs: number
  isPending: boolean
  showConfirm: boolean
  onChapterSelect: (id: number | null) => void
  onOffsetChange: (value: number) => void
  onPreview: () => void
  onApply: () => void
  onShowConfirm: () => void
  onCancelConfirm: () => void
}

export function ChapterTab({
  chapters,
  selectedChapterId,
  offsetMs,
  isPending,
  showConfirm,
  onChapterSelect,
  onOffsetChange,
  onPreview,
  onApply,
  onShowConfirm,
  onCancelConfirm,
}: ChapterTabProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
          Chapter
        </label>
        <select
          value={selectedChapterId ?? ''}
          onChange={(e) => onChapterSelect(e.target.value === '' ? null : Number(e.target.value))}
          style={{
            width: '100%',
            padding: '6px 8px',
            borderRadius: 4,
            border: '1px solid var(--border)',
            background: 'var(--bg-primary)',
            color: 'var(--text-primary)',
            fontSize: 13,
          }}
        >
          <option value="">Select chapter…</option>
          {chapters.map((ch: Chapter) => (
            <option key={ch.id} value={ch.id}>
              {ch.title} ({_formatMs(ch.start_ms)} – {_formatMs(ch.end_ms)})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label style={{ display: 'block', fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>
          Offset (ms)
        </label>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input
            type="number"
            value={offsetMs}
            onChange={(e) => onOffsetChange(Number(e.target.value))}
            style={{
              width: 90,
              padding: '6px 8px',
              borderRadius: 4,
              border: '1px solid var(--border)',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: 13,
              fontFamily: 'var(--font-mono)',
            }}
          />
          {[-500, -100, 100, 500].map((delta) => (
            <button
              key={delta}
              onClick={() => onOffsetChange(offsetMs + delta)}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: '1px solid var(--border)',
                background: 'var(--bg-primary)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {delta > 0 ? `+${delta}` : delta}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          disabled={selectedChapterId === null || isPending}
          onClick={onPreview}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
          style={{
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
          }}
        >
          {isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Eye size={12} />
          )}
          Preview
        </button>

        {showConfirm ? (
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--warning)' }}>
              This will modify the file. A backup will be created.
            </span>
            <button
              onClick={onApply}
              disabled={isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              Confirm
            </button>
            <button
              onClick={onCancelConfirm}
              className="px-2 py-1.5 rounded text-xs"
              style={{ color: 'var(--text-muted)' }}
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            disabled={selectedChapterId === null || isPending}
            onClick={onShowConfirm}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity"
            style={{
              backgroundColor: 'var(--accent)',
              opacity: selectedChapterId === null || isPending ? 0.5 : 1,
            }}
          >
            <Check size={12} />
            Apply
          </button>
        )}
      </div>
    </div>
  )
}
