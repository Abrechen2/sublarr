import type { ProcessingChange } from '@/api/client'

interface Props {
  changes: ProcessingChange[]
  onConfirm: () => void
  onCancel: () => void
  loading?: boolean
}

export function ProcessingPreviewPanel({ changes, onConfirm, onCancel, loading }: Props) {
  return (
    <div className="border border-zinc-700 rounded-lg bg-zinc-900 p-4 space-y-3 max-w-lg">
      <div className="text-sm font-medium text-zinc-300">
        {changes.length} Änderungen gefunden
      </div>

      <div className="max-h-64 overflow-y-auto space-y-1">
        {changes.map((c, i) => (
          <div key={i} className="text-xs font-mono grid grid-cols-2 gap-2 border-b border-zinc-800 pb-1">
            <span className="text-zinc-400 truncate">{c.original_text || '(leer)'}</span>
            <span className={c.modified_text ? 'text-yellow-400 truncate' : 'text-red-400'}>
              {c.modified_text || '(entfernt)'}
            </span>
          </div>
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={onConfirm}
          disabled={loading}
          className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50"
        >
          {loading ? 'Wird angewendet…' : 'Übernehmen'}
        </button>
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 text-white rounded"
        >
          Abbrechen
        </button>
      </div>
    </div>
  )
}
