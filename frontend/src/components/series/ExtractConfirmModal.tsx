import { AlertTriangle, ArchiveRestore } from 'lucide-react'

interface ExtractConfirmModalProps {
  readonly open: boolean
  readonly onConfirm: () => void
  readonly onCancel: () => void
}

export function ExtractConfirmModal({ open, onConfirm, onCancel }: ExtractConfirmModalProps) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(2px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="extract-confirm-title"
        className="w-full max-w-md rounded-xl shadow-2xl"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        {/* Header */}
        <div
          className="flex items-center gap-2.5 px-5 py-4"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <AlertTriangle size={16} style={{ color: 'var(--color-warning, #f59e0b)', flexShrink: 0 }} />
          <h2
            id="extract-confirm-title"
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            Embedded Untertitel extrahieren
          </h2>
        </div>

        {/* Body */}
        <div className="px-5 py-4 flex flex-col gap-3">
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            Alle eingebetteten Untertitel-Streams jeder Episode dieser Serie werden als Sidecar-Dateien
            (z.&nbsp;B. <code className="text-xs px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>.de.ass</code>)
            neben der Videodatei gespeichert.
          </p>

          {/* Warning box */}
          <div
            className="flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-xs leading-relaxed"
            style={{
              backgroundColor: 'rgba(245,158,11,0.08)',
              border: '1px solid rgba(245,158,11,0.25)',
              color: 'var(--text-secondary)',
            }}
          >
            <AlertTriangle
              size={13}
              style={{ color: 'var(--color-warning, #f59e0b)', flexShrink: 0, marginTop: '1px' }}
            />
            <span>
              Die extrahierten Streams werden anschließend <strong style={{ color: 'var(--text-primary)' }}>aus dem Videocontainer entfernt</strong>.
              Die Videodateien werden dabei verändert.
            </span>
          </div>

          {/* Trash info box */}
          <div
            className="flex items-start gap-2.5 rounded-lg px-3.5 py-3 text-xs leading-relaxed"
            style={{
              backgroundColor: 'var(--accent-bg)',
              border: '1px solid var(--accent-dim)',
              color: 'var(--text-secondary)',
            }}
          >
            <ArchiveRestore
              size={13}
              style={{ color: 'var(--accent)', flexShrink: 0, marginTop: '1px' }}
            />
            <span>
              Vor jeder Änderung wird automatisch ein Backup im{' '}
              <code className="text-xs px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>.sublarr/trash</code>
              {' '}Ordner neben der Videodatei angelegt. Die Originale können von dort wiederhergestellt werden.
            </span>
          </div>
        </div>

        {/* Footer */}
        <div
          className="flex justify-end gap-2 px-5 py-3.5"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <button
            onClick={onCancel}
            className="rounded-lg px-4 py-1.5 text-sm"
            style={{
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
              backgroundColor: 'transparent',
              cursor: 'pointer',
            }}
          >
            Abbrechen
          </button>
          <button
            autoFocus
            onClick={onConfirm}
            className="rounded-lg px-4 py-1.5 text-sm font-semibold"
            style={{
              backgroundColor: 'var(--color-warning, #f59e0b)',
              color: '#000',
              cursor: 'pointer',
              border: 'none',
            }}
          >
            Extrahieren
          </button>
        </div>
      </div>
    </div>
  )
}
