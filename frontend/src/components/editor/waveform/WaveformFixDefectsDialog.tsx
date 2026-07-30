/**
 * WaveformFixDefectsDialog — preview + confirm for the one-click
 * "fix safe defects" batch (waveform-expansion roadmap, Phase 1).
 *
 * Lists every proposed timing fix (overlap trim / tight-gap widening /
 * too-short extension) as a before → after row so the editor can inspect
 * the batch before it touches the cue list. Applying is a single atomic
 * edit on the modal's undo stack. Closes on ESC, X, or backdrop click —
 * same interaction contract as WaveformShortcutHelp.
 */

import { X, Wrench } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'

import type { CueTimingFix } from './fixSafeDefects'

export interface WaveformFixDefectsDialogProps {
  open: boolean
  fixes: CueTimingFix[]
  /** Defects detected in the file but not safely auto-fixable. */
  skippedCount: number
  onApply: () => void
  onClose: () => void
}

/** "M:SS.mmm" — compact but unambiguous for sub-second timing diffs. */
function fmtTime(sec: number): string {
  const total = Math.max(0, Math.round(sec * 1000))
  const ms = total % 1000
  const s = Math.floor(total / 1000) % 60
  const m = Math.floor(total / 60_000)
  return `${m}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

export function WaveformFixDefectsDialog({
  open,
  fixes,
  skippedCount,
  onApply,
  onClose,
}: WaveformFixDefectsDialogProps) {
  const { t } = useTranslation('editor')

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
      aria-labelledby="waveform-fix-defects-title"
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
              id="waveform-fix-defects-title"
              className="text-base font-semibold text-primary"
            >
              {t('waveform.fix.title')}
            </h2>
            <p className="text-xs text-muted mt-1">
              {t('waveform.fix.subtitle', { count: fixes.length })}
              {skippedCount > 0 && ` ${t('waveform.fix.skipped', { count: skippedCount })}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('waveform.fix.cancel')}
            className="text-muted hover:text-primary transition-colors p-1 rounded"
          >
            <X size={16} />
          </button>
        </div>

        <ul className="p-4 flex flex-col gap-1.5" data-testid="fix-defects-list">
          {fixes.map((fix) => (
            <li
              key={`${fix.cueIndex}-${fix.kind}`}
              className="flex items-center justify-between gap-3 text-xs"
            >
              <span className="text-primary">
                #{fix.cueIndex + 1} · {t(`waveform.fix.kind_${fix.kind}`)}
              </span>
              <span className="font-mono text-[11px] text-muted whitespace-nowrap">
                {fmtTime(fix.before.start)}–{fmtTime(fix.before.end)}
                {' → '}
                <span className="text-accent">
                  {fmtTime(fix.after.start)}–{fmtTime(fix.after.end)}
                </span>
              </span>
            </li>
          ))}
        </ul>

        <div className="flex items-center justify-end gap-2 p-4 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs font-medium bg-surface text-primary border border-border"
          >
            {t('waveform.fix.cancel')}
          </button>
          <button
            type="button"
            onClick={onApply}
            data-testid="fix-defects-apply"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-accent-bg text-accent border border-accent-dim"
          >
            <Wrench size={12} />
            {t('waveform.fix.apply', { count: fixes.length })}
          </button>
        </div>
      </div>
    </div>
  )
}
