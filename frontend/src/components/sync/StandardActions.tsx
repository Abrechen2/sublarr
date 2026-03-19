/**
 * Preview / Apply / Confirm action buttons for the offset, speed, and framerate tabs.
 */

import { Loader2, Check, Eye } from 'lucide-react'

interface StandardActionsProps {
  isPending: boolean
  showConfirm: boolean
  onPreview: () => void
  onApply: () => void
  onShowConfirm: () => void
  onCancelConfirm: () => void
}

export function StandardActions({
  isPending,
  showConfirm,
  onPreview,
  onApply,
  onShowConfirm,
  onCancelConfirm,
}: StandardActionsProps) {
  return (
    <div className="flex items-center gap-2 pt-1">
      <button
        onClick={onPreview}
        disabled={isPending}
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
          onClick={onShowConfirm}
          disabled={isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity"
          style={{
            backgroundColor: 'var(--accent)',
            opacity: isPending ? 0.5 : 1,
          }}
        >
          <Check size={12} />
          Apply
        </button>
      )}
    </div>
  )
}
