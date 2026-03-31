interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({ open, title, message, confirmLabel = 'Confirm', onConfirm, onCancel }: Props) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="w-full max-w-sm rounded-lg"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <h2 id="confirm-modal-title" className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
            {title}
          </h2>
        </div>
        <div className="px-4 py-3">
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{message}</p>
        </div>
        <div className="flex justify-end gap-2 px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
          <button
            onClick={onCancel}
            className="rounded px-3 py-1.5 text-sm"
            style={{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
          >
            Cancel
          </button>
          <button
            autoFocus
            onClick={onConfirm}
            className="rounded px-3 py-1.5 text-sm font-semibold"
            style={{ backgroundColor: 'var(--color-error)', color: '#fff' }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
