import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { GlossaryEntry } from '@/api/translation'

const mutate = vi.fn()
vi.mock('@/hooks/useApi', () => ({
  useGlossaryPresets: () => ({
    data: {
      presets: [
        {
          id: 'anime-en-de',
          name: 'Anime (English → German)',
          description: '',
          source_language: 'en',
          target_language: 'de',
          entries: [
            { source_term: 'Demon Lord', target_term: 'Dämonenfürst' },
            { source_term: 'Hero', target_term: 'Held' },
          ],
        },
      ],
    },
  }),
  useImportGlossaryPreset: () => ({ mutate, isPending: false, variables: undefined }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o && 'count' in o ? `${k}:${o.count}` : k),
  }),
}))

import { GlossaryPresetsCard } from '../GlossaryPresetsCard'

function entry(source_term: string, target_language: string | null = null): GlossaryEntry {
  return {
    id: 1, series_id: null, source_term, target_term: 'x', notes: '', term_type: 'other',
    confidence: null, approved: 1, target_language, created_at: '', updated_at: '',
  }
}

describe('GlossaryPresetsCard', () => {
  beforeEach(() => mutate.mockClear())

  it('imports only after the user clicks', () => {
    render(<GlossaryPresetsCard entries={[]} />)
    expect(mutate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByTestId('glossary-preset-import-anime-en-de'))
    expect(mutate).toHaveBeenCalledWith('anime-en-de', expect.anything())
  })

  it('counts only the terms the glossary does not have yet', () => {
    render(<GlossaryPresetsCard entries={[entry('demon lord', 'de')]} defaultOpen />)
    expect(screen.getByTestId('glossary-preset-import-anime-en-de').textContent).toContain('glossary_presets.import:1')
  })

  it('ignores a term kept for another target language', () => {
    render(<GlossaryPresetsCard entries={[entry('Demon Lord', 'fr')]} defaultOpen />)
    expect(screen.getByTestId('glossary-preset-import-anime-en-de').textContent).toContain('glossary_presets.import:2')
  })

  it('disables the button when everything is imported', () => {
    render(<GlossaryPresetsCard entries={[entry('Demon Lord'), entry('Hero', 'de')]} defaultOpen />)
    expect((screen.getByTestId('glossary-preset-import-anime-en-de') as HTMLButtonElement).disabled).toBe(true)
  })

  // A glossary that already has terms has seen the suggestions: the card
  // folds to its header so the term list below is not pushed down.
  it('starts folded when the glossary already has terms', () => {
    render(<GlossaryPresetsCard entries={[entry('Hero', 'de')]} />)
    expect(screen.queryByTestId('glossary-preset-import-anime-en-de')).toBeNull()
    fireEvent.click(screen.getByTestId('glossary-presets-toggle'))
    expect(screen.getByTestId('glossary-preset-import-anime-en-de')).toBeTruthy()
  })

  it('starts open for an empty glossary', () => {
    render(<GlossaryPresetsCard entries={[]} />)
    expect(screen.getByTestId('glossary-preset-import-anime-en-de')).toBeTruthy()
  })
})
