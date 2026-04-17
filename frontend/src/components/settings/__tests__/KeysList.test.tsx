import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import KeysList, { type KeysListProps } from '../KeysList'

const makeProps = (overrides: Partial<KeysListProps> = {}): KeysListProps => ({
  provider: 'opensubtitles',
  keys: [
    {
      id: 1,
      label: 'primary',
      tier: 'vip',
      enabled: true,
      last_used_at: null,
      last_429_at: null,
    },
    {
      id: 2,
      label: 'backup',
      tier: 'free',
      enabled: false,
      last_used_at: null,
      last_429_at: null,
    },
  ],
  onAdd: vi.fn(),
  onEdit: vi.fn(),
  onDelete: vi.fn(),
  ...overrides,
})

describe('KeysList', () => {
  test('renders a row per key with label + tier', () => {
    render(<KeysList {...makeProps()} />)
    expect(screen.getByTestId('key-row-1')).toHaveTextContent('primary')
    expect(screen.getByTestId('key-row-1')).toHaveTextContent('vip')
    expect(screen.getByTestId('key-row-2')).toHaveTextContent('backup')
  })

  test('delete-last uses distinct aria-label', () => {
    render(
      <KeysList {...makeProps({ keys: [makeProps().keys[0]] })} />,
    )
    const del = screen.getByTestId('delete-key-1')
    expect(del.getAttribute('aria-label')).toContain('last')
  })
})
