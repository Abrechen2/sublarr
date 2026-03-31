import { Loader2, Wand2, X } from 'lucide-react'
import { useBackendTemplates } from '@/hooks/useApi'

// ─── Template Picker Modal ────────────────────────────────────────────────────

export function TemplatePickerModal({
  onClose,
  onApply,
}: {
  onClose: () => void
  onApply: (backendName: string, config: Record<string, string>) => void
}) {
  const { data, isLoading } = useBackendTemplates()
  const templates = data?.templates ?? []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg shadow-2xl overflow-hidden"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <div className="flex items-center gap-2">
            <Wand2 size={16} style={{ color: 'var(--accent)' }} />
            <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Add from Template
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-2 max-h-96 overflow-y-auto">
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={20} className="animate-spin" style={{ color: 'var(--accent)' }} />
            </div>
          )}

          {!isLoading && templates.length === 0 && (
            <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
              No templates available.
            </div>
          )}

          {templates.map((tpl) => (
            <button
              key={tpl.name}
              onClick={() => {
                // Convert config_defaults to string values for the backend config API
                const config: Record<string, string> = {}
                for (const [k, v] of Object.entries(tpl.config_defaults)) {
                  config[k] = String(v)
                }
                onApply(tpl.backend_type, config)
              }}
              className="w-full text-left rounded-lg p-3 transition-all duration-150"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--accent-dim)'
                e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--border)'
                e.currentTarget.style.backgroundColor = 'var(--bg-primary)'
              }}
            >
              <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {tpl.display_name}
              </div>
              <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {tpl.description}
              </div>
              <div className="text-xs mt-1.5 font-mono" style={{ color: 'var(--text-secondary)' }}>
                {(tpl.config_defaults as Record<string, unknown>).base_url as string}
              </div>
            </button>
          ))}
        </div>

        {/* Footer note */}
        <div
          className="px-5 py-3 text-xs"
          style={{ borderTop: '1px solid var(--border)', color: 'var(--text-muted)' }}
        >
          Selecting a template pre-fills base URL, model, and context window. Add your API key after applying.
        </div>
      </div>
    </div>
  )
}
