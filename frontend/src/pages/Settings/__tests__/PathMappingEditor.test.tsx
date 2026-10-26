/**
 * PathMappingEditor.test.tsx — the mapping rows fit a phone screen.
 *
 * Found by the 1.18.0-rc.6 end-to-end test (R7): at 390 px Settings →
 * Connections overflowed by 132 px, because each row was a fixed
 * `1fr 1fr 2rem` grid whose inputs could not shrink below their natural
 * width. jsdom has no layout, so the responsive classes are checked.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PathMappingEditor } from '../PathMappingEditor'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

function renderEditor() {
  render(<PathMappingEditor value="/data/media=/mnt/user/media" onChange={vi.fn()} />)
}

describe('PathMappingEditor on a phone', () => {
  it('lets every input shrink to the row width', () => {
    renderEditor()
    const inputs = screen.getAllByRole('textbox')
    // Remote, local and the test-path input.
    expect(inputs).toHaveLength(3)
    for (const input of inputs) {
      expect(input.className).toContain('min-w-0')
    }
    expect(screen.getByDisplayValue('/data/media').className).toContain('w-full')
    expect(screen.getByDisplayValue('/mnt/user/media').className).toContain('w-full')
  })

  it('stacks remote and local below md and keeps three columns from md up', () => {
    renderEditor()
    const row = screen.getByDisplayValue('/data/media').parentElement as HTMLElement
    // No fixed inline columns: they cannot respond to the viewport.
    expect(row.style.gridTemplateColumns).toBe('')
    expect(row.className).toContain('grid-cols-[minmax(0,1fr)_2rem]')
    expect(row.className).toContain('md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem]')
    expect(screen.getByDisplayValue('/mnt/user/media').className).toContain('row-start-2')
  })

  it('keeps the column labels reachable on a phone', () => {
    renderEditor()
    expect(screen.getByLabelText('path_mapping.remote_path')).toHaveValue('/data/media')
    expect(screen.getByLabelText('path_mapping.local_path')).toHaveValue('/mnt/user/media')
  })
})
