/**
 * File picker for selecting 2-4 subtitle files to compare.
 *
 * Renders toggle buttons for each available file with teal accent
 * for selected state. Compare button enabled when 2-4 files selected.
 */

import { useState } from 'react'
import { Columns2, Check } from 'lucide-react'

interface AvailableFile {
  path: string
  label: string
}

interface ComparisonSelectorProps {
  availableFiles: AvailableFile[]
  onCompare: (paths: string[]) => void
  onClose?: () => void
  maxPanels?: number
}

export function ComparisonSelector({
  availableFiles,
  onCompare,
  onClose,
  maxPanels = 4,
}: ComparisonSelectorProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggleFile = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else if (next.size < maxPanels) {
        next.add(path)
      }
      return next
    })
  }

  const canCompare = selected.size >= 2 && selected.size <= maxPanels

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="flex items-center gap-2">
          <Columns2 size={16} style={{ color: 'var(--accent)' }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Select Files to Compare
          </span>
        </div>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {selected.size} of {Math.min(availableFiles.length, maxPanels)} selected
        </span>
      </div>

      {/* File list */}
      <div className="p-3 space-y-2">
        {availableFiles.map((file) => {
          const isSelected = selected.has(file.path)
          return (
            <button
              key={file.path}
              onClick={() => toggleFile(file.path)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left transition-colors"
              style={{
                backgroundColor: isSelected ? 'var(--accent-bg)' : 'var(--bg-primary)',
                border: `1px solid ${isSelected ? 'var(--accent-dim)' : 'var(--border)'}`,
                color: isSelected ? 'var(--accent)' : 'var(--text-secondary)',
              }}
            >
              <div
                className="w-5 h-5 rounded flex items-center justify-center shrink-0"
                style={{
                  backgroundColor: isSelected ? 'var(--accent)' : 'transparent',
                  border: isSelected ? 'none' : '2px solid var(--border)',
                }}
              >
                {isSelected && <Check size={12} className="text-white" />}
              </div>
              <span className="text-xs font-medium truncate">{file.label}</span>
            </button>
          )
        })}

        {availableFiles.length === 0 && (
          <div className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
            No subtitle files available for comparison.
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-end gap-2 px-4 py-3"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {onClose && (
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            Cancel
          </button>
        )}
        <button
          onClick={() => canCompare && onCompare(Array.from(selected))}
          disabled={!canCompare}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity"
          style={{
            backgroundColor: 'var(--accent)',
            opacity: canCompare ? 1 : 0.4,
            cursor: canCompare ? 'pointer' : 'not-allowed',
          }}
        >
          <Columns2 size={12} />
          Compare ({selected.size})
        </button>
      </div>
    </div>
  )
}
