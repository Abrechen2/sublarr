import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'

// Mock react-i18next — interpolate {{lang}} and {{format}} from options
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      const templates: Record<string, string> = {
        'subtitle_pills.missing': '{{lang}} fehlt',
        'subtitle_pills.missing_tooltip': 'Kein {{lang}}-Untertitel',
        'subtitle_pills.embedded_ass': '{{lang}} ASS ⬇',
        'subtitle_pills.embedded_ass_tooltip': 'Eingebetteter ASS-Track',
        'subtitle_pills.embedded_srt': '{{lang}} SRT ⬇',
        'subtitle_pills.embedded_srt_tooltip': 'Eingebetteter SRT-Track',
        'subtitle_pills.sidecar_ass': '{{lang}} ASS',
        'subtitle_pills.sidecar_ass_tooltip': 'ASS-Untertitel',
        'subtitle_pills.sidecar_srt': '{{lang}} SRT',
        'subtitle_pills.sidecar_srt_tooltip': 'SRT-Untertitel',
        'subtitle_pills.sidecar_srt_upgrade': '{{lang}} SRT ↑',
        'subtitle_pills.sidecar_srt_upgrade_tooltip': 'SRT Upgrade',
        'subtitle_pills.no_embedded': 'Nicht eingebettet',
        'subtitle_pills.no_embedded_tooltip': 'Keine eingebetteten Tracks',
        'subtitle_pills.embedded_track': '{{lang}} {{format}} ⬇',
        'subtitle_pills.embedded_track_tooltip': 'Eingebetteter Track',
      }
      let tpl = templates[key] ?? key
      if (opts) {
        Object.entries(opts).forEach(([k, v]) => { tpl = tpl.replaceAll(`{{${k}}}`, v) })
      }
      return tpl
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}))

const noEmbedded: Array<{ lang: string; format: string }> = []
const enAss = [{ lang: 'eng', format: 'ass' }]
const _enAssJaSrt = [{ lang: 'eng', format: 'ass' }, { lang: 'jpn', format: 'srt' }]
const threeLangs = [
  { lang: 'eng', format: 'ass' },
  { lang: 'jpn', format: 'srt' },
  { lang: 'fra', format: 'srt' },
]

describe('SubtitlePresencePills', () => {
  it('shows DE fehlt when existingSub is empty', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('DE fehlt')).toBeTruthy()
  })

  it('does not show embedded pills when nothing embedded', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    // v0.49.0: "Nicht eingebettet" pill was removed to reduce visual noise
    expect(screen.queryByText('Nicht eingebettet')).toBeNull()
    expect(screen.queryAllByTestId('embedded-pill')).toHaveLength(0)
  })

  it('shows DE SRT ↑ for srt existing_sub when upgrade enabled', () => {
    render(
      <SubtitlePresencePills
        existingSub="srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
        upgradeCandidate={true}
      />
    )
    expect(screen.getByText('DE SRT ↑')).toBeTruthy()
  })

  it('shows DE ASS ⬇ for embedded_ass', () => {
    render(
      <SubtitlePresencePills
        existingSub="embedded_ass"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('DE ASS ⬇')).toBeTruthy()
  })

  it('shows DE SRT ⬇ for embedded_srt', () => {
    render(
      <SubtitlePresencePills
        existingSub="embedded_srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('DE SRT ⬇')).toBeTruthy()
  })

  it('shows DE ASS for ass sidecar existing_sub', () => {
    render(
      <SubtitlePresencePills
        existingSub="ass"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('DE ASS')).toBeTruthy()
  })

  it('shows embedded lang pill', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('ENG ASS ⬇')).toBeTruthy()
  })

  it('shows +N button when more than 2 embedded', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={threeLangs}
      />
    )
    expect(screen.getByText('+1 ▾')).toBeTruthy()
  })

  it('expands overflow on click', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={threeLangs}
      />
    )
    const btn = screen.getByText('+1 ▾')
    fireEvent.click(btn)
    expect(screen.getByText('FRA SRT ⬇')).toBeTruthy()
  })

  it('sorts sourceLanguage first in right group (ISO 639-1 to 639-2 mapping)', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="es"
        embeddedLanguages={[{ lang: 'jpn', format: 'srt' }, { lang: 'spa', format: 'ass' }]}
      />
    )
    const pills = document.querySelectorAll('[data-testid="embedded-pill"]')
    expect(pills[0].textContent).toBe('SPA ASS ⬇')
    expect(pills[1].textContent).toBe('JPN SRT ⬇')
  })

  it('sorts eng first when sourceLanguage is en', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={[{ lang: 'jpn', format: 'srt' }, { lang: 'eng', format: 'ass' }]}
      />
    )
    const pills = document.querySelectorAll('[data-testid="embedded-pill"]')
    expect(pills[0].textContent).toBe('ENG ASS ⬇')
    expect(pills[1].textContent).toBe('JPN SRT ⬇')
  })

  it('shows SRT without arrow when upgrade is disabled', () => {
    render(
      <SubtitlePresencePills
        existingSub="srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
        upgradeCandidate={false}
      />
    )
    expect(screen.getByText('DE SRT')).toBeTruthy()
  })

  it('shows DE SRT ↑ when upgrade is enabled', () => {
    render(
      <SubtitlePresencePills
        existingSub="srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
        upgradeCandidate={true}
      />
    )
    expect(screen.getByText('DE SRT ↑')).toBeTruthy()
  })
})
