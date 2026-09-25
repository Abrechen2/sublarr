/**
 * TrackVerdictList — renders the per-track keep/strip verdicts returned by
 * `POST /api/v1/foreign-tracks/preview-file` (Task 9, track variant policy).
 *
 * One row per subtitle track: kept tracks show a check, stripped tracks show
 * an X plus a strikethrough reason label. Every reason code the backend can
 * send (see `services/foreign_tracks/select.py::TrackVerdict.reason`) must
 * have a translated label — the "labels every reason code" test guards that.
 */
import { CheckCircle2, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export const TRACK_REASONS = [
  'kept_main',
  'kept_forced',
  'kept_sdh',
  'kept_last_track',
  'kept_language',
  'stripped_language',
  'stripped_variant',
  'stripped_sidecar',
] as const
export type TrackReason = (typeof TRACK_REASONS)[number]

export interface TrackVerdict {
  index: number
  sub_index: number
  language: string
  fmt: 'ass' | 'text' | 'image'
  kind: 'full' | 'forced' | 'sdh'
  keep: boolean
  reason: TrackReason
}

export function TrackVerdictList({ verdicts }: { verdicts: TrackVerdict[] }) {
  const { t } = useTranslation('settings')
  return (
    <ul className="space-y-1 text-xs">
      {verdicts.map((v) => (
        <li
          key={v.index}
          data-testid={`verdict-${v.index}`}
          data-keep={String(v.keep)}
          className="flex items-center gap-2"
        >
          {v.keep ? (
            <CheckCircle2 size={13} className="text-success" />
          ) : (
            <XCircle size={13} className="text-error" />
          )}
          <span className="font-mono uppercase text-secondary w-8">{v.language.toUpperCase()}</span>
          <span className="font-mono uppercase text-muted w-10">{v.fmt}</span>
          <span className="text-muted w-14">{t(`cleanup.kind.${v.kind}`)}</span>
          <span className={v.keep ? 'text-foreground' : 'text-muted line-through'}>
            {t(`cleanup.reason.${v.reason}`)}
          </span>
        </li>
      ))}
    </ul>
  )
}
