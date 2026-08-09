import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'
import { ProviderEditor } from './ProviderEditor'

interface ProviderEditModalProps {
  provider: ProviderInfo
  cacheCount: number
  priority: number
  totalProviders: number
  fieldValues: Record<string, string>
  testResult?: { healthy: boolean; message: string } | 'testing'
  onFieldChange: (key: string, value: string) => void
  onTest: () => void
  onTestDownload?: () => void
  onToggle: () => void
  onClearCache: () => void
  onReEnable: () => void
  onRemove?: () => void
  isNew?: boolean
  onClose: () => void
}

/**
 * Modal wrapper around <ProviderEditor>. Kept for the legacy tile-grid path
 * (and any caller that wants a dialog presentation). The shared editor body
 * lives in ProviderEditor.tsx — both this modal and the new CollectionLayout
 * detail pane render the same content.
 */
export function ProviderEditModal({
  provider, cacheCount,
  fieldValues, testResult,
  onFieldChange, onTest, onTestDownload, onToggle,
  onClearCache, onReEnable, onRemove, isNew, onClose,
}: ProviderEditModalProps) {
  const { t } = useTranslation('settings')
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
        aria-labelledby="provider-edit-title"
        className="w-full max-w-lg flex flex-col rounded-lg overflow-hidden"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          maxHeight: '85vh',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 shrink-0"
          style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
        >
          <div>
            <p className="text-[11px] font-medium mb-0.5" style={{ color: 'var(--text-muted)' }}>
              {isNew ? t('provider_edit_modal.step_prefix') : ''}{t('provider_edit_modal.edit_provider')}
            </p>
            <h2 id="provider-edit-title" className="text-sm font-semibold capitalize" style={{ color: 'var(--text-primary)' }}>
              {provider.name.replace(/_/g, ' ')}
            </h2>
          </div>
          <button
            autoFocus
            onClick={onClose}
            aria-label={t('provider_edit_modal.close')}
            className="p-1.5 rounded transition-colors"
            style={{ color: 'var(--text-muted)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Editor body — scrollable */}
        <div className="overflow-y-auto flex-1 px-4 py-3">
          <ProviderEditor
            provider={provider}
            cacheCount={cacheCount}
            fieldValues={fieldValues}
            testResult={testResult}
            onFieldChange={onFieldChange}
            onTest={onTest}
            onTestDownload={onTestDownload}
            onToggle={onToggle}
            onClearCache={onClearCache}
            onReEnable={onReEnable}
            onRemove={onRemove}
            hideTitle
            footerExtra={
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded text-xs font-medium transition-all hover:opacity-80"
                style={{
                  backgroundColor: 'var(--accent)',
                  color: 'var(--bg-primary)',
                }}
              >
                {t('provider_edit_modal.close_button')}
              </button>
            }
          />
        </div>
      </div>
    </div>
  )
}
