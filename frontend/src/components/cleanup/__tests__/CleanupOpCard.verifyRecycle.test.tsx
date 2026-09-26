/**
 * "Delete the original right after a verified rewrite" is honoured by the sweep
 * since 1.15.0-rc.6, so the checkbox is live again (it was shown disabled in
 * rc.5 while no production path read it).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CleanupOpCard, type OpMeta } from '../CleanupOpCard'
import type { CleanupRule } from '@/lib/types'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const http = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue({ data: {} }),
  put: vi.fn().mockResolvedValue({ data: {} }),
  patch: vi.fn().mockResolvedValue({ data: {} }),
  post: vi.fn().mockResolvedValue({ data: {} }),
}))
vi.mock('@/api/core', () => ({ api: http, bootstrapApiKey: vi.fn() }))

const META: OpMeta = {
  ruleType: 'foreign_tracks',
  Icon: () => null,
  iconColor: '',
  iconBg: '',
  title: 'Foreign tracks',
  description: '',
  defaultName: 'Foreign tracks',
}

function rule(config: Record<string, unknown>): CleanupRule {
  return {
    id: 7,
    name: 'Foreign tracks',
    rule_type: 'foreign_tracks',
    config_json: config,
    enabled: true,
    schedule: 'manual',
    last_run_at: null,
  } as unknown as CleanupRule
}

function renderCard(config: Record<string, unknown>, onUpdate = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CleanupOpCard meta={META} rule={rule(config)} onToggle={vi.fn()} onUpdate={onUpdate} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByText('Foreign tracks'))
  return onUpdate
}

describe('CleanupOpCard — delete the original after a verified rewrite', () => {
  it('is an enabled checkbox that saves the NEW option key', () => {
    const onUpdate = renderCard({ keep_languages: ['de', 'en'] })
    const box = screen.getByText('cleanup_card.verify_recycle').closest('label')!.querySelector('input')!
    expect(box).not.toBeDisabled()
    expect(box).not.toBeChecked()
    fireEvent.click(box)
    expect(onUpdate).toHaveBeenCalledWith({
      config_json: { keep_languages: ['de', 'en'], delete_original_after_verify: true },
    })
  })

  it('does not arm a box ticked before the upgrade, and says why', () => {
    renderCard({ keep_languages: ['de', 'en'], verify_then_delete_backup: true })
    const box = screen.getByText('cleanup_card.verify_recycle').closest('label')!.querySelector('input')!
    expect(box).not.toBeChecked()
    expect(screen.getByText('cleanup_card.verify_recycle_legacy')).toBeInTheDocument()
  })

  it('shows no legacy notice once the user decided', () => {
    renderCard({ verify_then_delete_backup: true, delete_original_after_verify: false })
    expect(screen.queryByText('cleanup_card.verify_recycle_legacy')).toBeNull()
  })
})
