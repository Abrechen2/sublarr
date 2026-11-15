import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const entries = Array.from({ length: 40 }, (_, i) => ({
  id: i + 1, series_id: 7, source_term: `Term ${i}`, target_term: `Begriff ${i}`,
  notes: '', term_type: 'other', confidence: null, approved: 1, target_language: 'de',
  created_at: '', updated_at: '',
}))

const idle = { mutate: vi.fn(), isPending: false }
vi.mock('@/hooks/useApi', () => ({
  useGlossaryEntries: () => ({ data: { entries }, isLoading: false }),
  useCreateGlossaryEntry: () => idle,
  useUpdateGlossaryEntry: () => idle,
  useDeleteGlossaryEntry: () => idle,
  useSuggestGlossaryTerms: () => idle,
  useExportGlossaryTsv: () => idle,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

import { GlossaryPanel } from '../GlossaryPanel'

describe('GlossaryPanel (series)', () => {
  // A long series glossary scrolls inside its own box instead of stretching
  // the series page.
  it('puts the terms in a scroll box', () => {
    render(<GlossaryPanel seriesId={7} />)
    const box = screen.getByTestId('series-glossary-table-scroll')
    expect(box.className).toContain('overflow-y-auto')
    expect(box.className).toMatch(/max-h-/)
    expect(box.querySelectorAll('tbody tr')).toHaveLength(40)
  })
})
