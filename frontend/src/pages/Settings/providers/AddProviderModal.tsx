import { useEffect } from 'react'
import { X, ChevronRight, Key, User, Zap } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'
import { getCredentialBadge, getProviderDescription, type CredentialType } from './providerUtils'

interface AddProviderModalProps {
  availableProviders: ProviderInfo[]
  onSelect: (name: string) => void
  onClose: () => void
}

function CredentialBadge({ type }: { type: CredentialType }) {
  const config: Record<CredentialType, { label: string; color: string; Icon: typeof Zap }> = {
    free: { label: 'Gratis', color: 'var(--success)', Icon: Zap },
    api_key: { label: 'API Key', color: 'var(--warning)', Icon: Key },
    login: { label: 'Login', color: 'var(--accent)', Icon: User },
  }
  const { label, color, Icon } = config[type]

  return (
    <span
      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
        color,
      }}
    >
      <Icon size={9} />
      {label}
    </span>
  )
}

export function AddProviderModal({ availableProviders, onSelect, onClose }: AddProviderModalProps) {
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
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-provider-title"
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
              Schritt 1 von 2
            </p>
            <h2 id="add-provider-title" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              Provider hinzufügen
            </h2>
          </div>
          <button
            autoFocus
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
        <div className="py-1 max-h-96 overflow-y-auto">
          {availableProviders.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              Alle Provider sind bereits in der Liste.
            </p>
          ) : (
            availableProviders.map((provider) => (
              <button
                key={provider.name}
                onClick={() => onSelect(provider.name)}
                className="w-full flex items-center justify-between px-4 py-3 transition-colors text-left"
                style={{ color: 'var(--text-primary)' }}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
              >
                <div className="flex-1 min-w-0 mr-2">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium capitalize">
                      {provider.name.replace(/_/g, ' ')}
                    </span>
                    <CredentialBadge type={getCredentialBadge(provider.name)} />
                  </div>
                  <span className="text-[11px] block truncate" style={{ color: 'var(--text-muted)' }}>
                    {getProviderDescription(provider.name)}
                  </span>
                </div>
                <ChevronRight size={14} className="shrink-0" style={{ color: 'var(--text-muted)' }} />
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
