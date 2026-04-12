import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { CSSProperties, ReactNode } from 'react'

interface EmbeddedLang {
  lang: string
  format: string
}

interface SubtitlePresencePillsProps {
  existingSub: string
  targetLanguage: string
  sourceLanguage: string
  embeddedLanguages: EmbeddedLang[]
  upgradeCandidate?: boolean
}

const PILL_BASE: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 6px',
  borderRadius: 4,
  fontSize: 10,
  fontWeight: 700,
  fontFamily: 'var(--font-mono)',
  whiteSpace: 'nowrap',
  border: '1px solid',
}

const PILL_MISS: CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(239,68,68,0.1)',
  color: '#ef4444',
  borderColor: 'rgba(239,68,68,0.2)',
}

const PILL_SRT: CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(234,179,8,0.12)',
  color: '#eab308',
  borderColor: 'rgba(234,179,8,0.25)',
}

const PILL_EMB: CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(16,185,129,0.12)',
  color: '#10b981',
  borderColor: 'rgba(16,185,129,0.25)',
}

const PILL_OTHER: CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(29,184,212,0.12)',
  color: '#1db8d4',
  borderColor: 'rgba(29,184,212,0.25)',
}

const _PILL_NONE: CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(255,255,255,0.04)',
  color: 'var(--text-muted)',
  borderColor: 'rgba(255,255,255,0.07)',
  fontStyle: 'italic',
}

const INLINE_LIMIT = 2

// Map ISO 639-1 (2-letter, from Sublarr config) to ISO 639-2 (3-letter, from ffprobe tags)
const ISO1_TO_ISO2: Record<string, string> = {
  ar: 'ara', de: 'deu', en: 'eng', es: 'spa', fr: 'fra', it: 'ita',
  ja: 'jpn', ko: 'kor', nl: 'nld', no: 'nor', pl: 'pol', pt: 'por',
  ru: 'rus', sv: 'swe', tr: 'tur', zh: 'chi',
}

export function SubtitlePresencePills({
  existingSub,
  targetLanguage,
  sourceLanguage,
  embeddedLanguages,
  upgradeCandidate = false,
}: SubtitlePresencePillsProps) {
  const { t } = useTranslation('library')
  const [expanded, setExpanded] = useState(false)
  const lang = targetLanguage.toUpperCase()

  // Left pill — target language status
  let leftPill: ReactNode
  if (existingSub === 'embedded_ass') {
    leftPill = <span style={PILL_EMB} title={t('subtitle_pills.embedded_ass_tooltip', { lang })}>{t('subtitle_pills.embedded_ass', { lang })}</span>
  } else if (existingSub === 'embedded_srt') {
    leftPill = <span style={PILL_EMB} title={t('subtitle_pills.embedded_srt_tooltip', { lang })}>{t('subtitle_pills.embedded_srt', { lang })}</span>
  } else if (existingSub === 'ass') {
    leftPill = <span style={PILL_EMB} title={t('subtitle_pills.sidecar_ass_tooltip', { lang })}>{t('subtitle_pills.sidecar_ass', { lang })}</span>
  } else if (existingSub === 'srt') {
    if (upgradeCandidate) {
      leftPill = <span style={PILL_SRT} title={t('subtitle_pills.sidecar_srt_upgrade_tooltip', { lang })}>{t('subtitle_pills.sidecar_srt_upgrade', { lang })}</span>
    } else {
      leftPill = <span style={PILL_SRT} title={t('subtitle_pills.sidecar_srt_tooltip', { lang })}>{t('subtitle_pills.sidecar_srt', { lang })}</span>
    }
  } else {
    leftPill = <span style={PILL_MISS} title={t('subtitle_pills.missing_tooltip', { lang })}>{t('subtitle_pills.missing', { lang })}</span>
  }

  // Right group — sort sourceLanguage first, then alphabetically
  const sourceLang3 = ISO1_TO_ISO2[sourceLanguage] ?? sourceLanguage
  const sorted = [...embeddedLanguages].sort((a, b) => {
    const aIsSource = a.lang === sourceLanguage || a.lang === sourceLang3
    const bIsSource = b.lang === sourceLanguage || b.lang === sourceLang3
    if (aIsSource && !bIsSource) return -1
    if (!aIsSource && bIsSource) return 1
    return a.lang.localeCompare(b.lang)
  })

  const inline = sorted.slice(0, INLINE_LIMIT)
  const overflow = sorted.slice(INLINE_LIMIT)

  const rightContent =
    embeddedLanguages.length === 0 ? null : (
      inline.map((e) => {
        const eLang = e.lang.toUpperCase()
        const eFormat = e.format.toUpperCase()
        return (
          <span key={e.lang} data-testid="embedded-pill" style={PILL_OTHER}
            title={t('subtitle_pills.embedded_track_tooltip', { lang: eLang, format: eFormat })}>
            {t('subtitle_pills.embedded_track', { lang: eLang, format: eFormat })}
          </span>
        )
      })
    )

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {leftPill}
      {rightContent !== null && (
        <span style={{ width: 1, height: 14, background: 'var(--border)', margin: '0 2px', flexShrink: 0 }} />
      )}
      {rightContent}
      {overflow.length > 0 && (
        <>
          <button
            onClick={() => setExpanded((e) => !e)}
            style={{
              ...PILL_BASE,
              background: 'rgba(255,255,255,0.06)',
              color: 'var(--text-muted)',
              borderColor: 'rgba(255,255,255,0.1)',
              cursor: 'pointer',
            }}
          >
            +{overflow.length} {expanded ? '▲' : '▾'}
          </button>
          {expanded && (
            <div
              style={{
                width: '100%',
                display: 'flex',
                gap: 4,
                flexWrap: 'wrap',
                marginTop: 4,
                padding: '6px 8px',
                background: 'var(--bg-surface)',
                borderRadius: 4,
                border: '1px solid var(--border)',
              }}
            >
              {overflow.map((e) => {
                const eLang = e.lang.toUpperCase()
                const eFormat = e.format.toUpperCase()
                return (
                  <span key={e.lang} data-testid="embedded-pill" style={PILL_OTHER}
                    title={t('subtitle_pills.embedded_track_tooltip', { lang: eLang, format: eFormat })}>
                    {t('subtitle_pills.embedded_track', { lang: eLang, format: eFormat })}
                  </span>
                )
              })}
            </div>
          )}
        </>
      )}
    </div>
  )
}
