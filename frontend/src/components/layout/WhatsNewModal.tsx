/** What's-New modal (V1.6 #5) — per-version release highlights. */
import { useTranslation } from 'react-i18next'
import { Sparkles, X } from 'lucide-react'
import { WHATS_NEW } from '@/content/whatsNew'

interface Props {
  open: boolean
  version: string | null
  onDismiss: () => void
}

export function WhatsNewModal({ open, version, onDismiss }: Props) {
  const { t } = useTranslation('common')
  if (!open || !version) return null
  const items = WHATS_NEW[version] ?? []

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onDismiss() }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="whatsnew-title"
        className="w-full max-w-lg rounded-lg flex flex-col"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', maxHeight: '85vh' }}
      >
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2">
            <Sparkles size={16} style={{ color: 'var(--accent)' }} />
            <h2 id="whatsnew-title" className="font-semibold text-sm text-primary">
              {t('whatsnew.title', { version })}
            </h2>
          </div>
          <button onClick={onDismiss} className="p-1 rounded" style={{ color: 'var(--text-muted)' }} title={t('whatsnew.close')}>
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-3 space-y-2 overflow-auto">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <div key={item.titleKey} className="flex items-start gap-3 rounded-lg p-3 bg-page border border-border">
                <div className="mt-0.5 shrink-0 rounded-md p-1.5" style={{ backgroundColor: 'var(--accent-bg)' }}>
                  <Icon size={15} style={{ color: 'var(--accent)' }} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-primary">{t(item.titleKey)}</div>
                  <div className="text-[11px] text-muted mt-0.5">{t(item.descKey)}</div>
                </div>
              </div>
            )
          })}
        </div>

        <div className="flex justify-end px-4 py-3" style={{ borderTop: '1px solid var(--border)' }}>
          <button
            onClick={onDismiss}
            className="rounded px-3 py-1.5 text-xs font-medium text-white"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {t('whatsnew.got_it')}
          </button>
        </div>
      </div>
    </div>
  )
}
