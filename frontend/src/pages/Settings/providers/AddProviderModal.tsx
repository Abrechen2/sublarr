import { useEffect } from 'react'
import { X, ChevronRight } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'

interface AddProviderModalProps {
  disabledProviders: ProviderInfo[]
  onSelect: (name: string) => void
  onClose: () => void
}

export function AddProviderModal({ disabledProviders, onSelect, onClose }: AddProviderModalProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.65)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-sm rounded-lg overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div>
            <p className="text-[11px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>
              Provider
            </p>
            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Provider aktivieren
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Provider list */}
        <div className="py-1 max-h-80 overflow-y-auto">
          {disabledProviders.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              Alle Provider sind bereits aktiviert.
            </p>
          ) : (
            disabledProviders.map((provider) => {
              const fieldCount = provider.config_fields.length
              return (
                <button
                  key={provider.name}
                  onClick={() => onSelect(provider.name)}
                  className="w-full flex items-center justify-between px-4 py-2.5 transition-colors text-left"
                  style={{ color: 'var(--text-primary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                >
                  <div>
                    <span className="text-sm font-medium capitalize block">
                      {provider.name.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {fieldCount === 0
                        ? 'Keine Zugangsdaten erforderlich'
                        : `${fieldCount} Feld${fieldCount !== 1 ? 'er' : ''} konfigurieren`}
                    </span>
                  </div>
                  <ChevronRight size={14} style={{ color: 'var(--text-muted)' }} />
                </button>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
