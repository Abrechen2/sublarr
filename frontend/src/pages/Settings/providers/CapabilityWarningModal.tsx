import { AlertTriangle } from 'lucide-react'

const HIGH_RISK = new Set(['filesystem', 'subprocess'])

interface Props {
  plugin: { name: string; display_name: string; capabilities: string[] }
  onConfirm: () => void
  onCancel: () => void
}

export function CapabilityWarningModal({ plugin, onConfirm, onCancel }: Props) {
  const risky = plugin.capabilities.filter((c) => HIGH_RISK.has(c))

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cap-warning-title"
        className="bg-gray-900 border border-yellow-600 rounded-lg p-6 max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-yellow-400 shrink-0" />
          <h2 id="cap-warning-title" className="text-lg font-semibold">
            Community Plugin — Elevated Permissions
          </h2>
        </div>
        <p className="text-gray-300 text-sm mb-3">
          <strong>{plugin.display_name}</strong> declares the following capabilities:
        </p>
        <ul className="mb-4 space-y-1">
          {risky.map((cap) => (
            <li key={cap} className="text-yellow-400 text-sm font-mono bg-yellow-400/10 px-2 py-1 rounded">
              {cap}
            </li>
          ))}
        </ul>
        <p className="text-gray-400 text-sm mb-6">
          Community code runs inside the Sublarr process. Only install if you trust the source.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            autoFocus
            onClick={onCancel}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded"
          >
            Install anyway
          </button>
        </div>
      </div>
    </div>
  )
}
