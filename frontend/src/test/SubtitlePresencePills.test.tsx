import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SubtitlePresencePills } from '@/pages/wanted/SubtitlePresencePills'

const noEmbedded: Array<{ lang: string; format: string }> = []
const enAss = [{ lang: 'eng', format: 'ass' }]
const enAssJaSrt = [{ lang: 'eng', format: 'ass' }, { lang: 'jpn', format: 'srt' }]
const threeLangs = [
  { lang: 'eng', format: 'ass' },
  { lang: 'jpn', format: 'srt' },
  { lang: 'fra', format: 'srt' },
]

describe('SubtitlePresencePills', () => {
  it('shows DE ✗ when existingSub is empty', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('DE ✗')).toBeTruthy()
  })

  it('shows Kein Sub when nothing embedded', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={noEmbedded}
      />
    )
    expect(screen.getByText('Kein Sub')).toBeTruthy()
  })

  it('shows DE SRT ↑ for srt existing_sub', () => {
    render(
      <SubtitlePresencePills
        existingSub="srt"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('DE SRT ↑')).toBeTruthy()
  })

  it('shows DE ↓ ASS for embedded_ass', () => {
    render(
      <SubtitlePresencePills
        existingSub="embedded_ass"
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={enAss}
      />
    )
    expect(screen.getByText('DE ↓ ASS')).toBeTruthy()
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
    expect(screen.getByText('ENG ↓ ASS')).toBeTruthy()
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
    expect(screen.getByText('FRA ↓ SRT')).toBeTruthy()
  })

  it('sorts sourceLanguage first in right group', () => {
    render(
      <SubtitlePresencePills
        existingSub=""
        targetLanguage="de"
        sourceLanguage="en"
        embeddedLanguages={[{ lang: 'jpn', format: 'srt' }, { lang: 'eng', format: 'ass' }]}
      />
    )
    const pills = document.querySelectorAll('[data-testid="embedded-pill"]')
    expect(pills[0].textContent).toBe('ENG ↓ ASS')
    expect(pills[1].textContent).toBe('JPN ↓ SRT')
  })
})
