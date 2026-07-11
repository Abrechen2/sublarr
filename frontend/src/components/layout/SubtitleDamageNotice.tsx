/**
 * One-time notice about the HI-removal data-loss bug (see CHANGELOG 1.6.6/1.7.0).
 *
 * Sublarr's HI removal shipped an English interjection word list ("um", "uh",
 * "eh", "nah", ...) and cut every occurrence out of the subtitle text — in every
 * language. In German those are ordinary words, so downloaded subtitles came back
 * with words missing. Anyone who ran auto-processing with HI removal enabled may
 * have damaged sidecars on disk, and the .bak backups are not a way out.
 *
 * Since 1.7.0 there is a repair tool, so the notice does not just apologise — it
 * takes the user straight to it in one click. This is a data-integrity apology,
 * not a feature announcement, hence its own modal rather than a WhatsNew entry.
 */
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Wrench } from 'lucide-react'

interface Props {
  open: boolean
  onDismiss: () => void
}

export function SubtitleDamageNotice({ open, onDismiss }: Props) {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  if (!open) return null

  const goToRepair = () => {
    onDismiss()
    navigate('/settings/system#subtitle-repair')
  }

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0,0,0,0.7)' }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="damage-title"
        className="w-full max-w-xl rounded-lg flex flex-col"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--danger, #dc2626)',
          maxHeight: '85vh',
        }}
      >
        <div
          className="flex items-center gap-2 px-4 py-3"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <AlertTriangle size={16} style={{ color: 'var(--danger, #dc2626)' }} />
          <h2 id="damage-title" className="font-semibold text-sm text-primary">
            {t('damage_notice.title')}
          </h2>
        </div>

        <div className="px-4 py-3 space-y-3 overflow-auto text-xs text-primary leading-relaxed">
          <p className="font-medium">{t('damage_notice.apology')}</p>
          <p className="text-muted">{t('damage_notice.what_happened')}</p>

          <div className="rounded-md p-3 bg-page border border-border font-mono text-[11px]">
            <div className="text-muted">{t('damage_notice.example_before')}</div>
            <div>
              darf ich dich <span style={{ color: 'var(--accent)' }}>um</span> eine Sache bitten?
            </div>
            <div className="text-muted mt-1.5">{t('damage_notice.example_after')}</div>
            <div>darf ich dich&nbsp;&nbsp;eine Sache bitten?</div>
          </div>

          <p className="text-muted">{t('damage_notice.who_is_affected')}</p>
          <p className="text-muted">{t('damage_notice.fixed')}</p>

          <div
            className="rounded-md p-3 border"
            style={{ borderColor: 'var(--accent)', backgroundColor: 'var(--accent-bg)' }}
          >
            <p className="font-medium text-primary">{t('damage_notice.repair_available')}</p>
            <p className="text-muted mt-1">{t('damage_notice.repair_how')}</p>
          </div>
        </div>

        <div
          className="flex justify-between items-center px-4 py-3"
          style={{ borderTop: '1px solid var(--border)' }}
        >
          <button onClick={onDismiss} className="rounded px-3 py-1.5 text-xs text-muted">
            {t('damage_notice.later')}
          </button>
          <button
            onClick={goToRepair}
            className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-white"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Wrench size={13} />
            {t('damage_notice.open_repair')}
          </button>
        </div>
      </div>
    </div>
  )
}
