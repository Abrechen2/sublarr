/**
 * Widget settings modal for toggling dashboard widget visibility
 * and resetting layout to defaults.
 */
import { X, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDashboardStore } from '@/stores/dashboardStore'
import { WIDGET_REGISTRY } from './widgetRegistry'

interface WidgetSettingsModalProps {
  open: boolean
  onClose: () => void
}

export function WidgetSettingsModal({ open, onClose }: WidgetSettingsModalProps) {
  const { t } = useTranslation('dashboard')
  const hiddenWidgets = useDashboardStore((s) => s.hiddenWidgets)
  const toggleWidget = useDashboardStore((s) => s.toggleWidget)
  const resetToDefault = useDashboardStore((s) => s.resetToDefault)

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="w-full max-w-md rounded-xl overflow-hidden shadow-2xl"
          style={{
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: '1px solid var(--border)' }}
          >
            <div>
              <h2 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {t('widgets.settings_title')}
              </h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {t('widgets.settings_description')}
              </p>
            </div>
            <button
              onClick={onClose}
              className="p-1 rounded hover:opacity-80 transition-opacity"
              style={{ color: 'var(--text-muted)' }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Widget List */}
          <div className="px-5 py-3 space-y-1 max-h-[60vh] overflow-y-auto">
            {WIDGET_REGISTRY.map((widget) => {
              const Icon = widget.icon
              const isHidden = hiddenWidgets.includes(widget.id)

              return (
                <div
                  key={widget.id}
                  className="flex items-center justify-between py-2 px-2 rounded-md transition-colors"
                  style={{ backgroundColor: 'var(--bg-primary)' }}
                >
                  <div className="flex items-center gap-3">
                    <Icon
                      size={16}
                      style={{ color: isHidden ? 'var(--text-muted)' : 'var(--accent)' }}
                    />
                    <span
                      className="text-sm"
                      style={{
                        color: isHidden ? 'var(--text-muted)' : 'var(--text-primary)',
                      }}
                    >
                      {t(widget.titleKey)}
                    </span>
                  </div>

                  {/* Toggle Switch */}
                  <button
                    onClick={() => toggleWidget(widget.id)}
                    className="relative w-9 h-5 rounded-full transition-colors duration-200"
                    style={{
                      backgroundColor: isHidden
                        ? 'var(--bg-surface)'
                        : 'var(--accent)',
                      border: '1px solid var(--border)',
                    }}
                    role="switch"
                    aria-checked={!isHidden}
                  >
                    <span
                      className="absolute top-0.5 w-3.5 h-3.5 rounded-full transition-transform duration-200"
                      style={{
                        backgroundColor: isHidden
                          ? 'var(--text-muted)'
                          : 'var(--bg-primary)',
                        transform: isHidden ? 'translateX(2px)' : 'translateX(18px)',
                      }}
                    />
                  </button>
                </div>
              )
            })}
          </div>

          {/* Footer */}
          <div
            className="px-5 py-3 flex justify-end"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            <button
              onClick={() => {
                resetToDefault()
                onClose()
              }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 hover:opacity-80"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              <RotateCcw size={12} />
              {t('widgets.reset_layout')}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
