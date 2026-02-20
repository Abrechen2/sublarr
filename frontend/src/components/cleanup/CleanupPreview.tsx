/**
 * CleanupPreview -- Shows files that would be affected by a cleanup operation.
 *
 * Displays a list of files with sizes and actions, total size that would be freed,
 * and confirm/cancel buttons for the user to approve the operation.
 */
import { useTranslation } from 'react-i18next'
import { Trash2, X, AlertTriangle } from 'lucide-react'
import type { CleanupPreviewData } from '@/lib/types'

interface CleanupPreviewProps {
  preview: CleanupPreviewData
  onConfirm: () => void
  onCancel: () => void
  isConfirming?: boolean
}

/** Format bytes into human-readable KB/MB/GB */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function CleanupPreview({ preview, onConfirm, onCancel, isConfirming = false }: CleanupPreviewProps) {
  const { t } = useTranslation('settings')

  return (
    <div
      className="rounded-lg p-4 space-y-4"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--warning)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <AlertTriangle size={16} style={{ color: 'var(--warning)' }} />
        <h4 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('cleanup.preview.title', 'Cleanup Preview')}
        </h4>
      </div>

      {/* Summary */}
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--text-secondary)' }}>
        <span>
          {preview.total_files} {t('cleanup.preview.files', 'files')}
        </span>
        <span style={{ color: 'var(--warning)' }}>
          {formatBytes(preview.total_size_bytes)} {t('cleanup.preview.willBeFreed', 'will be freed')}
        </span>
      </div>

      {/* File list */}
      <div
        className="max-h-60 overflow-auto rounded-md"
        style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
      >
        {preview.files.map((file) => (
          <div
            key={file.path}
            className="flex items-center gap-3 px-3 py-1.5 text-xs"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
              style={{
                backgroundColor: file.action === 'delete' ? 'rgba(239,68,68,0.1)' : 'var(--accent-bg)',
                color: file.action === 'delete' ? 'var(--error)' : 'var(--accent)',
              }}
            >
              {file.action}
            </span>
            <span
              className="flex-1 truncate"
              style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}
              title={file.path}
            >
              {file.path}
            </span>
            <span
              className="shrink-0 tabular-nums"
              style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}
            >
              {formatBytes(file.size_bytes)}
            </span>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onConfirm}
          disabled={isConfirming}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-opacity disabled:opacity-50"
          style={{ backgroundColor: 'var(--error)' }}
        >
          <Trash2 size={12} />
          {isConfirming
            ? t('cleanup.preview.confirming', 'Deleting...')
            : t('cleanup.preview.confirm', 'Confirm Delete')}
        </button>
        <button
          onClick={onCancel}
          disabled={isConfirming}
          className="flex items-center gap-1 px-3 py-1.5 rounded-md text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          <X size={12} />
          {t('cleanup.preview.cancel', 'Cancel')}
        </button>
      </div>
    </div>
  )
}
