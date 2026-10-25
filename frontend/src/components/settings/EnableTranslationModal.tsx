import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Languages, X } from 'lucide-react'
import { useUpdateConfig } from '@/hooks/useApi'

interface EnableTranslationModalProps {
  readonly onClose: () => void
}

export function EnableTranslationModal({ onClose }: EnableTranslationModalProps) {
  const { t } = useTranslation('editor')
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
          aria-label={t('close')}
        >
          <X size={16} />
        </button>

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-lg shrink-0 w-10 h-10 bg-accent-bg">
            <Languages size={20} className="text-accent" />
          </div>
          <div className="font-bold text-base text-foreground">
            {t('enable_translation_modal.title')}
          </div>
        </div>

        {/* Body */}
        <div className="text-sm leading-relaxed text-secondary">
          <p>{t('enable_translation_modal.body')}</p>
          <p className="mt-2">{t('enable_translation_modal.requirement')}</p>
        </div>

        {/* Acknowledgement */}
        <label className="flex items-start gap-3 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={understood}
            onChange={(e) => setUnderstood(e.target.checked)}
            className="mt-0.5 shrink-0 w-4 h-4 accent-accent"
          />
          <span className="text-sm text-secondary">
            {t('enable_translation_modal.understand_checkbox')}
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
            {t('enable_translation_modal.cancel')}
          </button>
          <button
            onClick={handleEnable}
            disabled={!understood || updateConfig.isPending}
            className="px-4 py-2 rounded-md text-sm font-semibold bg-accent text-white border border-transparent disabled:opacity-50"
          >
            {t('enable_translation_modal.enable_button')}
          </button>
        </div>
      </div>
    </div>
  )
}
