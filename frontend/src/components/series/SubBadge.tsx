import React from 'react'

export function SubBadge({ lang, format }: { lang: string; format: string }) {
  // Three visual states:
  //  teal   = optimal   (ass / embedded_ass)
  //  amber  = upgradeable (srt / embedded_srt — present but not best format)
  //  orange = missing   (no subtitle file at all)
  const isOptimal = format === 'ass' || format === 'embedded_ass'
  const isUpgradeable = format === 'srt' || format === 'embedded_srt'
  const isEmbedded = format === 'embedded_ass' || format === 'embedded_srt'
  const hasFile = isOptimal || isUpgradeable

  const bg = isOptimal ? 'var(--accent-bg)' : isUpgradeable ? 'var(--upgrade-bg)' : 'var(--warning-bg)'
  const color = isOptimal ? 'var(--accent)' : isUpgradeable ? 'var(--upgrade)' : 'var(--warning)'
  const border = isOptimal
    ? '1px solid var(--accent-dim)'
    : isUpgradeable
      ? '1px solid rgba(167,139,250,0.4)'
      : '1px solid rgba(245,158,11,0.3)'

  const label = isEmbedded ? format.replace('embedded_', '') + '⊕' : format
  const title = hasFile
    ? `${lang.toUpperCase()} (${format.toUpperCase()}${isEmbedded ? ' — eingebettet' : ''}${isUpgradeable ? ' — upgradeable zu ASS' : ''})`
    : `${lang.toUpperCase()} fehlt`

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: bg, color, border }}
      title={title}
    >
      {lang.toUpperCase()}
      {hasFile && (
        <span style={{ opacity: 0.6, fontSize: '9px' }}>{label}</span>
      )}
    </span>
  )
}
