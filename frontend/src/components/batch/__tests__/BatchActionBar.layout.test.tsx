/**
 * VM test of 1.14.3-rc.4: after "select all" on a 390 px phone the bar was
 * 844 px wide, pinned to the centre with a translate, so only 3 of 8 buttons
 * were on screen (2 of 8 at 320 px). Layout itself cannot be measured in jsdom;
 * these tests pin the classes that keep the bar inside the viewport on phones
 * and the centred pill from md up. The measured proof is a browser check.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BatchActionBar } from '../BatchActionBar'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/stores/selectionStore', () => ({
  useSelectionStore: (selector: (s: unknown) => unknown) =>
    selector({
      getCount: () => 37,
      getSelectedArray: () => [1, 2, 3],
      clearSelection: vi.fn(),
    }),
}))

vi.mock('@/hooks/useApi', () => ({
  useBatchAction: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useBatchTranslate: () => ({ mutateAsync: vi.fn(), isPending: false }),
}))

vi.mock('@/api/client', () => ({ batchExtractEmbedded: vi.fn() }))
vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

function bar() {
  render(<BatchActionBar scope="wanted" actions={['ignore', 'unignore', 'blacklist', 'export', 'extract', 'translate', 'reset_attempts']} />)
  return screen.getByRole('toolbar')
}

describe('BatchActionBar layout', () => {
  it('spans the viewport with a gutter and wraps on phones', () => {
    const cls = bar().className.split(/\s+/)
    expect(cls).toEqual(expect.arrayContaining(['left-3', 'right-3', 'flex-wrap']))
    expect(cls).not.toContain('left-1/2')
    expect(cls).not.toContain('-translate-x-1/2')
  })

  it('sits above the bottom navigation on phones', () => {
    expect(bar().className.split(/\s+/)).toContain('bottom-24')
  })

  it('drops below the hidden bottom navigation from md, but keeps wrapping at tablet width', () => {
    // VM test of 1.14.4-rc.2: at 768 px the pill was 844 px wide and ran from
    // -38 to 806 px, "Clear selection" off screen.
    const cls = bar().className.split(/\s+/)
    expect(cls).toContain('md:bottom-6')
    expect(cls).not.toContain('md:left-1/2')
    expect(cls).not.toContain('md:flex-nowrap')
  })

  it('keeps the centred single-row pill from lg up', () => {
    const cls = bar().className.split(/\s+/)
    expect(cls).toEqual(
      expect.arrayContaining(['lg:left-1/2', 'lg:right-auto', 'lg:-translate-x-1/2', 'lg:flex-nowrap']),
    )
  })

  it('still renders every action and the clear button', () => {
    bar()
    expect(screen.getAllByRole('button')).toHaveLength(8)
  })
})
