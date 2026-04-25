import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ScopeTree } from '../ScopeTree'
import type { ScopesTree } from '@/api/profilesOverrides'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, fb?: string) => fb ?? k }),
}))

const sampleTree: ScopesTree = {
  profiles: [
    {
      id: 1, name: 'Anime DE', is_default: true,
      series: [{ id: 100, title: 'Frieren' }],
      movies: [{ id: 200, title: 'Spirited Away' }],
    },
  ],
  unassigned_series: [{ id: 999, title: 'Orphan Series' }],
  unassigned_movies: [],
}

describe('ScopeTree', () => {
  it('renders Global node always at top', () => {
    render(<ScopeTree tree={sampleTree} selected={null} onSelect={() => {}} onProfileAction={() => {}} />)
    expect(screen.getByText(/global default/i)).toBeInTheDocument()
  })

  it('renders profile and its series under it', () => {
    render(<ScopeTree tree={sampleTree} selected={null} onSelect={() => {}} onProfileAction={() => {}} />)
    expect(screen.getByText('Anime DE')).toBeInTheDocument()
    expect(screen.getByText('Frieren')).toBeInTheDocument()
  })

  it('renders unassigned series in dedicated section', () => {
    render(<ScopeTree tree={sampleTree} selected={null} onSelect={() => {}} onProfileAction={() => {}} />)
    expect(screen.getByText(/series.*no profile/i)).toBeInTheDocument()
    expect(screen.getByText('Orphan Series')).toBeInTheDocument()
  })

  it('clicking a series fires onSelect with type+id', () => {
    const onSelect = vi.fn()
    render(<ScopeTree tree={sampleTree} selected={null} onSelect={onSelect} onProfileAction={() => {}} />)
    fireEvent.click(screen.getByText('Frieren'))
    expect(onSelect).toHaveBeenCalledWith({ type: 'series', id: 100 })
  })

  it('clicking the Add-profile button fires onProfileAction("add")', () => {
    const onProfileAction = vi.fn()
    render(<ScopeTree tree={sampleTree} selected={null} onSelect={() => {}} onProfileAction={onProfileAction} />)
    fireEvent.click(screen.getByRole('button', { name: /add profile/i }))
    expect(onProfileAction).toHaveBeenCalledWith({ kind: 'add' })
  })
})
