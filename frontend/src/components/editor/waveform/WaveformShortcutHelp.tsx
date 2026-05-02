/**
 * WaveformShortcutHelp — modal listing every Aegisub-style hotkey
 * (Plan B8 Task 5 Step 3).
 *
 * Opens via the `?` shortcut or the toolbar button. Renders a centred
 * dialog with shortcuts grouped by category. Closes on ESC, on the X
 * button, or on backdrop click.
 *
 * Shortcuts data lives in `keymap.ts`; the i18n keys it references live
 * in `frontend/src/i18n/locales/{en,de}/editor.json` under
 * `editor.waveform.shortcut.*` and `editor.waveform.shortcut_group.*`.
 */

import { X } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import {
  WAVEFORM_SHORTCUTS,
  WAVEFORM_SHORTCUT_GROUPS,
  type WaveformShortcutGroup,
} from './keymap'

export interface WaveformShortcutHelpProps {
  open: boolean
  onClose: () => void
}

export function WaveformShortcutHelp({ open, onClose }: WaveformShortcutHelpProps) {
  const { t } = useTranslation('editor')

  // ESC to close — local listener so we don't compete with the global keymap
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="waveform-shortcut-help-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-secondary border border-border rounded-md shadow-xl w-[min(560px,92vw)] max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 p-4 border-b border-border">
          <div>
            <h2
              id="waveform-shortcut-help-title"
              className="text-base font-semibold text-primary"
            >
              {t('waveform.shortcut.title')}
            </h2>
            <p className="text-xs text-muted mt-1">{t('waveform.shortcut.subtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('waveform.shortcut_close')}
            className="text-muted hover:text-primary transition-colors p-1 rounded"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4 flex flex-col gap-5">
          {WAVEFORM_SHORTCUT_GROUPS.map((group) => (
            <ShortcutGroup key={group} group={group} />
          ))}
        </div>
      </div>
    </div>
  )
}

interface ShortcutGroupProps {
  group: WaveformShortcutGroup
}

function ShortcutGroup({ group }: ShortcutGroupProps) {
  const { t } = useTranslation('editor')
  const items = WAVEFORM_SHORTCUTS.filter((s) => s.group === group)
  if (items.length === 0) return null

  return (
    <section>
      <h3 className="text-[11px] uppercase tracking-wider text-muted mb-2">
        {t(`waveform.shortcut_group.${group}`)}
      </h3>
      <ul className="flex flex-col gap-1.5">
        {items.map((s) => (
          <li
            key={s.action}
            className="flex items-center justify-between gap-3 text-xs"
          >
            <span className="text-primary">{t(`waveform.shortcut.${s.labelKey}`)}</span>
            <kbd className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-primary border border-border text-primary">
              {s.display}
            </kbd>
          </li>
        ))}
      </ul>
    </section>
  )
}
