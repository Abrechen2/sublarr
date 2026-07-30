/**
 * Shared subtitle flag badges — MT, uploader trust, HI, forced, source and
 * sync state. Extracted from InteractiveSearchModal so list views (History,
 * Wanted, episode panels) can show the same signals without opening a modal.
 */

import { useTranslation } from 'react-i18next'

const base = 'text-[10px] px-1 rounded whitespace-nowrap'

export function TrustBadge({ bonus, uploaderName }: { bonus: number; uploaderName?: string }) {
  const { t } = useTranslation('common')
  if (bonus <= 0) return null
  return (
    <span
      className={`${base} text-emerald-400 bg-emerald-400/10`}
      title={uploaderName ? `Uploader: ${uploaderName}` : t('badges.trusted_uploader')}
    >
      +{Math.round(bonus)} Trust
    </span>
  )
}

export function MTBadge({ confidence }: { confidence?: number }) {
  const { t } = useTranslation('common')
  return (
    <span className={`${base} text-orange-400 bg-orange-400/10`} title={t('badges.machine_translated')}>
      {confidence && confidence > 0 ? `MT ${Math.round(confidence)}%` : 'MT'}
    </span>
  )
}

export function HIBadge() {
  const { t } = useTranslation('common')
  return (
    <span className={`${base} text-amber-400 bg-amber-400/10`} title={t('badges.hearing_impaired')}>
      HI
    </span>
  )
}

export function ForcedBadge() {
  const { t } = useTranslation('common')
  return (
    <span className={`${base} text-blue-400 bg-blue-400/10`} title={t('badges.forced')}>
      F
    </span>
  )
}

export function SyncedBadge({ engine }: { engine?: string }) {
  const { t } = useTranslation('common')
  return (
    <span
      className={`${base} text-teal-400 bg-teal-400/10`}
      title={engine ? t('badges.synced_with', { engine }) : t('badges.synced')}
    >
      ⇄ {t('badges.synced')}
    </span>
  )
}

/**
 * Provenance badge for downloaded subtitles. `provider` is the default
 * source and renders nothing — only the notable origins get a badge.
 */
export function SourceBadge({ source }: { source?: string | null }) {
  const { t } = useTranslation('common')
  if (!source || source === 'provider') return null
  const styles: Record<string, string> = {
    whisper: 'text-violet-400 bg-violet-400/10',
    manual: 'text-slate-400 bg-slate-400/10',
    machine_translation: 'text-orange-400 bg-orange-400/10',
    combined: 'text-cyan-400 bg-cyan-400/10',
  }
  const labels: Record<string, string> = {
    whisper: t('badges.source_whisper'),
    manual: t('badges.source_manual'),
    machine_translation: t('badges.source_mt'),
    combined: t('badges.source_combined'),
  }
  return (
    <span className={`${base} ${styles[source] ?? 'text-slate-400 bg-slate-400/10'}`} title={t('badges.source_tooltip')}>
      {labels[source] ?? source}
    </span>
  )
}

export interface ResultFlags {
  hearing_impaired?: boolean
  forced?: boolean
  machine_translated?: boolean
  mt_confidence?: number
  uploader_trust_bonus?: number
  uploader_name?: string
}

/** Renders the full flag row for a provider search result. */
export function ResultFlagBadges({ flags }: { flags: ResultFlags }) {
  const showMT = flags.machine_translated || (flags.mt_confidence !== undefined && flags.mt_confidence > 0)
  return (
    <span className="inline-flex items-center gap-1">
      {flags.uploader_trust_bonus !== undefined && flags.uploader_trust_bonus > 0 && (
        <TrustBadge bonus={flags.uploader_trust_bonus} uploaderName={flags.uploader_name} />
      )}
      {showMT && <MTBadge confidence={flags.mt_confidence} />}
      {flags.hearing_impaired && <HIBadge />}
      {flags.forced && <ForcedBadge />}
    </span>
  )
}
