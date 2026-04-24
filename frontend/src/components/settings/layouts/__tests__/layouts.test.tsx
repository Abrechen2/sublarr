/**
 * Smoke tests for the three Settings layout scaffolds.
 *
 * Purpose: verify the Props API contracts (slot rendering, selection
 * callbacks, health-rail visibility) so a future migration cannot
 * silently break the templates. Not a full visual regression suite —
 * that comes once the reference pages migrate.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CollectionLayout } from '../CollectionLayout'
import { FormLayout } from '../FormLayout'
import type { FormSectionDef } from '../FormLayout'
import { RulesLayout } from '../RulesLayout'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key, // tests use keys directly
  }),
}))

// ─── A: CollectionLayout ────────────────────────────────────────────────

describe('CollectionLayout', () => {
  type Item = { id: string; name: string }

  const items: Item[] = [
    { id: 'a', name: 'Alpha' },
    { id: 'b', name: 'Beta' },
  ]

  const baseProps = {
    items,
    selectedId: 'a',
    getItemId: (it: Item) => it.id,
    renderListItem: (it: Item) => <span>{it.name}</span>,
    renderDetail: (it: Item | null) =>
      it ? <div data-testid="detail">Detail: {it.name}</div> : null,
    onSelect: vi.fn(),
  }

  it('renders list + detail + marks the selected row active', () => {
    render(<CollectionLayout {...baseProps} />)
    const rows = screen.getAllByTestId('collection-item')
    expect(rows).toHaveLength(2)
    expect(rows[0].getAttribute('data-active')).toBe('true')
    expect(rows[1].getAttribute('data-active')).toBe('false')
    expect(screen.getByTestId('detail').textContent).toBe('Detail: Alpha')
  })

  it('calls onSelect with the item id when a row is clicked', () => {
    const onSelect = vi.fn()
    render(<CollectionLayout {...baseProps} onSelect={onSelect} />)
    fireEvent.click(screen.getAllByTestId('collection-item')[1])
    expect(onSelect).toHaveBeenCalledWith('b')
  })

  it("allows onSelect to accept null (deselect contract)", () => {
    // TypeScript-level guarantee: onSelect can now be invoked with null.
    const onSelect = vi.fn<(id: string | null) => void>()
    render(<CollectionLayout {...baseProps} onSelect={onSelect} />)
    onSelect(null)
    expect(onSelect).toHaveBeenCalledWith(null)
  })

  it('hides the health rail slot when no healthRail prop is given', () => {
    render(<CollectionLayout {...baseProps} />)
    expect(screen.queryByTestId('collection-rail')).toBeNull()
  })

  it('shows the health rail when provided', () => {
    render(
      <CollectionLayout
        {...baseProps}
        healthRail={<div data-testid="rail-payload">rail</div>}
      />,
    )
    expect(screen.getByTestId('collection-rail')).toBeInTheDocument()
    expect(screen.getByTestId('rail-payload')).toBeInTheDocument()
  })

  it('renders emptyState when items is empty', () => {
    render(
      <CollectionLayout
        {...baseProps}
        items={[]}
        selectedId={null}
        emptyState={<div data-testid="empty">Nothing yet</div>}
      />,
    )
    expect(screen.getByTestId('empty')).toBeInTheDocument()
    expect(screen.queryAllByTestId('collection-item')).toHaveLength(0)
  })

  it('renders the listHeader slot when provided', () => {
    render(
      <CollectionLayout
        {...baseProps}
        listHeader={
          <div data-testid="header-payload">
            <span>Providers (10)</span>
            <button data-testid="header-add">+ Add</button>
          </div>
        }
      />,
    )
    expect(screen.getByTestId('collection-list-header')).toBeInTheDocument()
    expect(screen.getByTestId('header-payload')).toBeInTheDocument()
    // Caller composes the header — no built-in listTitle/onAdd surface anymore.
    expect(screen.getByTestId('header-add')).toBeInTheDocument()
  })
})

// ─── B: FormLayout ──────────────────────────────────────────────────────

describe('FormLayout', () => {
  const sections: FormSectionDef[] = [
    { id: 's1', titleKey: 'settings.test.one' },
    { id: 's2', titleKey: 'settings.test.two', advancedCount: 2 },
    { id: 's3', titleKey: 'settings.test.expert', expertOnly: true },
  ]

  it('renders children + TOC entries for non-expert sections by default', () => {
    render(
      <FormLayout sections={sections}>
        <section id="s1">One body</section>
        <section id="s2">Two body</section>
      </FormLayout>,
    )
    const tocItems = screen.getAllByTestId('form-toc-item')
    expect(tocItems).toHaveLength(2) // expert hidden
    // Mock t() returns the key verbatim, so titleKey strings appear in TOC text.
    expect(tocItems[0].textContent).toContain('settings.test.one')
    expect(tocItems[1].textContent).toContain('settings.test.two')
    expect(screen.getByText('One body')).toBeInTheDocument()
  })

  it('reveals expert-only sections in the TOC when expertMode=true', () => {
    render(
      <FormLayout sections={sections} expertMode>
        <section id="s1">body</section>
      </FormLayout>,
    )
    expect(screen.getAllByTestId('form-toc-item')).toHaveLength(3)
  })

  it('highlights the active section in the TOC', () => {
    render(
      <FormLayout sections={sections} activeSectionId="s2">
        <section id="s1">body</section>
      </FormLayout>,
    )
    const items = screen.getAllByTestId('form-toc-item')
    expect(items[0].getAttribute('data-active')).toBe('false')
    expect(items[1].getAttribute('data-active')).toBe('true')
  })

  it('shows the expert-mode hint when expert sections are hidden', () => {
    render(
      <FormLayout sections={sections}>
        <section id="s1">body</section>
      </FormLayout>,
    )
    expect(screen.getByTestId('form-expert-hint')).toBeInTheDocument()
  })

  it('renders the health rail slot when provided', () => {
    render(
      <FormLayout
        sections={sections.slice(0, 2)}
        healthRail={<div data-testid="rail">rail</div>}
      >
        <section id="s1">body</section>
      </FormLayout>,
    )
    expect(screen.getByTestId('form-rail')).toBeInTheDocument()
  })

  it('calls onSectionChange and suppresses default nav when a TOC link is clicked', () => {
    const onSectionChange = vi.fn()
    render(
      <FormLayout sections={sections} onSectionChange={onSectionChange}>
        <section id="s1">body</section>
      </FormLayout>,
    )
    const link = screen.getAllByTestId('form-toc-item')[1]
    fireEvent.click(link)
    expect(onSectionChange).toHaveBeenCalledWith('s2')
  })

  it('falls back to native anchor navigation when onSectionChange is omitted', () => {
    render(
      <FormLayout sections={sections}>
        <section id="s1">body</section>
      </FormLayout>,
    )
    const link = screen.getAllByTestId('form-toc-item')[0]
    expect(link.getAttribute('href')).toBe('#s1')
  })
})

// ─── C: RulesLayout ─────────────────────────────────────────────────────

describe('RulesLayout', () => {
  const baseProps = {
    scopeTree: <div data-testid="tree">tree</div>,
    resolvedHeader: <div data-testid="resolved">resolved</div>,
    overrideWidget: <div data-testid="override">override</div>,
  }

  it('renders scope tree + resolved header + override widget', () => {
    render(<RulesLayout {...baseProps} />)
    expect(screen.getByTestId('tree')).toBeInTheDocument()
    expect(screen.getByTestId('resolved')).toBeInTheDocument()
    expect(screen.getByTestId('override')).toBeInTheDocument()
  })

  it('renders otherRules only when provided', () => {
    const { rerender } = render(<RulesLayout {...baseProps} />)
    expect(screen.queryByTestId('rules-other')).toBeNull()

    rerender(
      <RulesLayout
        {...baseProps}
        otherRules={<div data-testid="other">other</div>}
      />,
    )
    expect(screen.getByTestId('rules-other')).toBeInTheDocument()
  })

  it('inserts a 3-column grid when a health rail is provided', () => {
    render(
      <RulesLayout
        {...baseProps}
        healthRail={<div data-testid="rail">rail</div>}
      />,
    )
    expect(screen.getByTestId('rules-rail')).toBeInTheDocument()
  })

  it('renders the breadcrumb slot above the layout grid when provided', () => {
    render(
      <RulesLayout
        {...baseProps}
        breadcrumb={<span data-testid="crumbs">Global › Profile › Series</span>}
      />,
    )
    expect(screen.getByTestId('rules-breadcrumb')).toBeInTheDocument()
    expect(screen.getByTestId('crumbs').textContent).toContain('Series')
  })
})
