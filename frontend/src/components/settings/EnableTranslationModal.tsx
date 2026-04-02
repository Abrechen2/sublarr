import { useState } from 'react'
import { FlaskConical, X } from 'lucide-react'
import { useUpdateConfig } from '@/hooks/useApi'

interface EnableTranslationModalProps {
  readonly onClose: () => void
}

export function EnableTranslationModal({ onClose }: EnableTranslationModalProps) {
  const [understood, setUnderstood] = useState(false)
  const updateConfig = useUpdateConfig()

  function handleEnable() {
    updateConfig.mutate({ translation_enabled: 'true' }, { onSuccess: onClose })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="relative flex flex-col gap-5 rounded-xl"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          padding: 28,
          maxWidth: 480,
          width: '90vw',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1 rounded"
          style={{ color: 'var(--text-muted)' }}
          aria-label="Close"
        >
          <X size={16} />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center rounded-lg shrink-0"
            style={{ width: 40, height: 40, backgroundColor: 'var(--warning-bg)' }}
          >
            <FlaskConical size={20} style={{ color: 'var(--warning)' }} />
          </div>
          <div>
            <div className="font-bold text-base" style={{ color: 'var(--text-primary)' }}>
              Translation aktivieren
            </div>
            <div
              className="text-xs font-semibold rounded-full px-2 py-0.5 inline-block mt-0.5"
              style={{ backgroundColor: 'var(--warning-bg)', color: 'var(--warning)' }}
            >
              BETA
            </div>
          </div>
        </div>

        {/* Warning body */}
        <div
          className="rounded-lg text-sm leading-relaxed"
          style={{
            padding: '12px 16px',
            backgroundColor: 'var(--warning-bg)',
            border: '1px solid var(--warning)',
            color: 'var(--text-secondary)',
          }}
        >
          <p>
            Die KI-Übersetzungsfunktion ist experimentell und funktioniert aktuell nicht
            zuverlässig genug für den produktiven Einsatz. Ergebnisse können stark
            variieren — abhängig von Modell, Prompt und Eingabequalität.
          </p>
          <p className="mt-2">
            Voraussetzung: Ein laufender <strong>Ollama</strong>-Server mit einem konfigurierten Modell.
          </p>
        </div>

        {/* Checkbox */}
        <label className="flex items-start gap-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={understood}
            onChange={(e) => setUnderstood(e.target.checked)}
            className="mt-0.5 shrink-0"
            style={{ accentColor: 'var(--accent)', width: 16, height: 16 }}
          />
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Ich verstehe, dass dies eine Beta-Funktion ist, und nutze sie auf eigenes Risiko.
          </span>
        </label>

        {/* Actions */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm font-medium"
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleEnable}
            disabled={!understood || updateConfig.isPending}
            className="px-4 py-2 rounded-md text-sm font-semibold"
            style={{
              backgroundColor: understood ? 'var(--accent)' : 'var(--bg-elevated)',
              color: understood ? '#fff' : 'var(--text-muted)',
              border: '1px solid transparent',
              opacity: !understood || updateConfig.isPending ? 0.5 : 1,
            }}
          >
            Enable Translation
          </button>
        </div>
      </div>
    </div>
  )
}
