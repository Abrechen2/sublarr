import { useState } from 'react'

interface EmbeddedLang {
  lang: string
  format: string
}

interface SubtitlePresencePillsProps {
  existingSub: string
  targetLanguage: string
  sourceLanguage: string
  embeddedLanguages: EmbeddedLang[]
}

const PILL_BASE: React.CSSProperties = {
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

const PILL_MISS: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(239,68,68,0.1)',
  color: '#ef4444',
  borderColor: 'rgba(239,68,68,0.2)',
}

const PILL_SRT: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(234,179,8,0.12)',
  color: '#eab308',
  borderColor: 'rgba(234,179,8,0.25)',
}

const PILL_EMB: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(16,185,129,0.12)',
  color: '#10b981',
  borderColor: 'rgba(16,185,129,0.25)',
}

const PILL_OTHER: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(29,184,212,0.12)',
  color: '#1db8d4',
  borderColor: 'rgba(29,184,212,0.25)',
}

const PILL_NONE: React.CSSProperties = {
  ...PILL_BASE,
  background: 'rgba(255,255,255,0.04)',
  color: 'var(--text-muted)',
  borderColor: 'rgba(255,255,255,0.07)',
  fontStyle: 'italic',
}

const INLINE_LIMIT = 2

export function SubtitlePresencePills({
  existingSub,
  targetLanguage,
  sourceLanguage,
  embeddedLanguages,
}: SubtitlePresencePillsProps) {
  const [expanded, setExpanded] = useState(false)
  const lang = targetLanguage.toUpperCase()

  // Left pill — target language status
  let leftPill: React.ReactNode
  if (existingSub === 'embedded_ass') {
    leftPill = <span style={PILL_EMB}>{lang} ↓ ASS</span>
  } else if (existingSub === 'embedded_srt') {
    leftPill = <span style={PILL_EMB}>{lang} ↓ SRT</span>
  } else if (existingSub === 'ass') {
    leftPill = <span style={PILL_EMB}>{lang} ASS</span>
  } else if (existingSub === 'srt') {
    leftPill = <span style={PILL_SRT}>{lang} SRT ↑</span>
  } else {
    leftPill = <span style={PILL_MISS}>{lang} ✗</span>
  }

  // Right group — sort sourceLanguage first, then alphabetically
  const sorted = [...embeddedLanguages].sort((a, b) => {
    const aIsSource = a.lang === sourceLanguage || a.lang.startsWith(sourceLanguage)
    const bIsSource = b.lang === sourceLanguage || b.lang.startsWith(sourceLanguage)
    if (aIsSource && !bIsSource) return -1
    if (!aIsSource && bIsSource) return 1
    return a.lang.localeCompare(b.lang)
  })

  const inline = sorted.slice(0, INLINE_LIMIT)
  const overflow = sorted.slice(INLINE_LIMIT)

  const rightContent =
    embeddedLanguages.length === 0 ? (
      <span style={PILL_NONE}>Kein Sub</span>
    ) : (
      inline.map((e, i) => (
        <span key={i} data-testid="embedded-pill" style={PILL_OTHER}>
          {e.lang.toUpperCase()} ↓ {e.format.toUpperCase()}
        </span>
      ))
    )

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
      {leftPill}
      <span
        style={{ width: 1, height: 14, background: 'var(--border)', margin: '0 2px', flexShrink: 0 }}
      />
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
              {overflow.map((e, i) => (
                <span key={i} data-testid="embedded-pill" style={PILL_OTHER}>
                  {e.lang.toUpperCase()} ↓ {e.format.toUpperCase()}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
