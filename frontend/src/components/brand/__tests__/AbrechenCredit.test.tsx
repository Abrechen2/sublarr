import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import deCommon from '../../../i18n/locales/de/common.json'
import enCommon from '../../../i18n/locales/en/common.json'
import { AbrechenCredit } from '../AbrechenCredit'

const dictionaries = { de: deCommon, en: enCommon } as const
let language: keyof typeof dictionaries = 'en'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      let v: unknown = dictionaries[language]
      for (const part of key.split('.')) {
        v = typeof v === 'object' && v !== null ? (v as Record<string, unknown>)[part] : undefined
      }
      return typeof v === 'string' ? v : key
    },
    i18n: { language },
  }),
}))

describe('AbrechenCredit', () => {
  beforeEach(() => {
    language = 'en'
  })

  it('links to the English site with an accessible name in English', () => {
    render(<AbrechenCredit />)
    const link = screen.getByRole('link', { name: 'A project by abrechen2' })
    expect(link).toHaveAttribute('href', 'https://www.abrechen2.de/en/')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('links to the German site with an accessible name in German', () => {
    language = 'de'
    render(<AbrechenCredit />)
    const link = screen.getByRole('link', { name: 'Ein Projekt von abrechen2' })
    expect(link).toHaveAttribute('href', 'https://www.abrechen2.de/')
  })

  it('draws the wordmark as an outlined SVG, never as text', () => {
    render(<AbrechenCredit />)
    const logo = screen.getByRole('img', { name: 'abrechen2' })
    expect(logo.tagName.toLowerCase()).toBe('svg')
    expect(logo).toHaveAttribute('viewBox', '60 40 820 120')
    expect(logo).toHaveAttribute('width', '128')
    expect(logo.querySelectorAll('path')).toHaveLength(3)
    expect(logo.querySelector('text')).toBeNull()
  })
})
