import type { ReactNode } from 'react'
import type { EpisodeInfo } from '@/lib/types'

export type EpisodeRowStatus = 'ok' | 'missing' | 'no-file'

/** Derive a row status from an episode and its target languages. */
export function getRowStatus(ep: EpisodeInfo, targetLanguages: string[]): EpisodeRowStatus {
  if (!ep.has_file) return 'no-file'
  if (targetLanguages.length === 0) return 'ok'
  const hasMissing = targetLanguages.some((lang) => {
    const fmt = ep.subtitles[lang]
    return fmt == null || fmt === ''
  })
  return hasMissing ? 'missing' : 'ok'
}

const STATUS_BORDER: Record<EpisodeRowStatus, string> = {
  ok: 'var(--success)',
  missing: 'var(--error)',
  'no-file': 'var(--border)',
}

interface EpisodeRowProps {
  ep: EpisodeInfo
  targetLanguages: string[]
  children: ReactNode
}

/**
 * Wraps episode row content with a status-colored left border.
 * ok = green, missing = red, no-file = neutral.
 */
export function EpisodeRow({ ep, targetLanguages, children }: EpisodeRowProps) {
  const status = getRowStatus(ep, targetLanguages)
  const borderColor = STATUS_BORDER[status]

  return (
    <div
      style={{
        borderLeft: `2px solid ${borderColor}`,
        transition: 'border-color 0.2s ease',
      }}
      data-status={status}
    >
      {children}
    </div>
  )
}

/** Format badge for subtitle format strings (ass / srt / embedded variants). */
export function FormatBadge({ format }: { format: string }) {
  const isAss = format === 'ass' || format === 'embedded_ass'
  const isSrt = format === 'srt' || format === 'embedded_srt'
  const isEmbedded = format === 'embedded_ass' || format === 'embedded_srt'

  const label = isEmbedded ? format.replace('embedded_', '') + '⊕' : format

  const style = isAss
    ? { backgroundColor: 'rgba(16,185,129,0.1)', color: 'var(--success)' }
    : isSrt
      ? { backgroundColor: 'rgba(167,139,250,0.1)', color: '#a78bfa' }
      : { backgroundColor: 'var(--bg-surface)', color: 'var(--text-muted)' }

  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
      style={{ ...style, fontFamily: 'var(--font-mono)' }}
    >
      {label}
    </span>
  )
}
