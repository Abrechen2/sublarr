import { useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { GLOBAL_SHORTCUTS, getActionTemplatesForRoute } from './quickActionDefinitions'

// ─── Types ───────────────────────────────────────────────────────────────────

interface KeyboardShortcutsModalProps {
  readonly open: boolean
  readonly onClose: () => void
}

// ─── Shortcut Row ────────────────────────────────────────────────────────────

function ShortcutRow({ label, shortcut }: { readonly label: string; readonly shortcut: string }) {
  return (
    <div
      className="flex items-center justify-between py-1.5"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <span className="text-sm" style={{ color: 'var(--text)' }}>{label}</span>
      <kbd
        className="rounded px-2 py-0.5 font-mono text-xs"
        style={{
          backgroundColor: 'var(--bg-secondary)',
          color: 'var(--text-secondary)',
          border: '1px solid var(--border)',
        }}
      >
        {shortcut}
      </kbd>
    </div>
  )
}

// ─── Section ─────────────────────────────────────────────────────────────────

function ShortcutSection({
  title,
  children,
}: {
  readonly title: string
  readonly children: React.ReactNode
}) {
  return (
    <div className="mb-4">
      <h3
        className="mb-2 text-xs font-semibold uppercase tracking-wider"
        style={{ color: 'var(--text-secondary)' }}
      >
        {title}
      </h3>
      <div className="space-y-0">{children}</div>
    </div>
  )
}

// ─── Modal ───────────────────────────────────────────────────────────────────

export function KeyboardShortcutsModal({ open, onClose }: KeyboardShortcutsModalProps) {
  const { pathname } = useLocation()
  const { t } = useTranslation('common')

  const pageActions = getActionTemplatesForRoute(pathname)

  const navigationShortcuts = GLOBAL_SHORTCUTS.filter((s) => s.category === 'navigation')
  const globalShortcuts = GLOBAL_SHORTCUTS.filter((s) => s.category === 'global')

  // Close on Escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    },
    [onClose],
  )

  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0"
        style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal */}
      <div
        className="relative z-10 w-full max-w-md rounded-lg p-6 shadow-xl"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          border: '1px solid var(--border)',
        }}
        role="dialog"
        aria-modal="true"
        aria-label={t('shortcuts.title')}
      >
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--text)' }}>
            {t('shortcuts.title')}
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 transition-colors hover:opacity-70"
            style={{ color: 'var(--text-secondary)' }}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Navigation shortcuts */}
        <ShortcutSection title={t('shortcuts.navigation')}>
          {navigationShortcuts.map((s) => (
            <ShortcutRow
              key={s.id}
              label={t(s.labelKey.replace('common:', ''))}
              shortcut={s.shortcut}
            />
          ))}
        </ShortcutSection>

        {/* Global shortcuts */}
        <ShortcutSection title={t('shortcuts.global')}>
          {globalShortcuts.map((s) => (
            <ShortcutRow
              key={s.id}
              label={t(s.labelKey.replace('common:', ''))}
              shortcut={s.shortcut}
            />
          ))}
        </ShortcutSection>

        {/* Page-specific shortcuts */}
        <ShortcutSection title={t('shortcuts.page_actions')}>
          {pageActions.length > 0 ? (
            pageActions.map((action) => (
              <ShortcutRow
                key={action.id}
                label={t(action.labelKey.replace('common:', ''))}
                shortcut={action.shortcut}
              />
            ))
          ) : (
            <p className="text-sm italic" style={{ color: 'var(--text-secondary)' }}>
              {t('shortcuts.no_page_actions')}
            </p>
          )}
        </ShortcutSection>
      </div>
    </div>
  )
}
