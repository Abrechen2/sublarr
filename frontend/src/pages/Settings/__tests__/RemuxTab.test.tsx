/**
 * RemuxTab.test.tsx — Tests for Remux settings tab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { RemuxTab } from '../RemuxTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

import enSettings from '../../../i18n/locales/en/settings.json'
import enCommon from '../../../i18n/locales/en/common.json'

function lookupKey(ns: Record<string, unknown>, key: string): string | undefined {
  const parts = key.split('.')
  let v: unknown = ns
  for (const p of parts) {
    if (typeof v !== 'object' || v === null) return undefined
    v = (v as Record<string, unknown>)[p]
  }
  return typeof v === 'string' ? v : undefined
}

vi.mock('react-i18next', () => ({
  useTranslation: (ns?: string) => ({
    t: (key: string, opts?: string | Record<string, unknown>) => {
      if (typeof opts === 'string') return opts
      if (opts !== undefined && typeof opts === 'object' && 'count' in opts)
        return `${key}:${String(opts.count)}`
      const dict = ns === 'settings' ? enSettings : enCommon
      return lookupKey(dict, key) ?? key
    },
  }),
}))

const mutateMock = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({
    data: {
      remux_trash_dir: '/media/trash',
      remux_backup_retention_days: '7',
      remux_use_reflink: 'false',
      remux_arr_pause_enabled: 'true',
    },
  }),
  useUpdateConfig: () => ({ mutate: mutateMock, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

const cleanupMock = vi.fn()
vi.mock('@/api/library', () => ({
  cleanupRemuxBackups: (dry: boolean) => cleanupMock(dry),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderTab() {
  return render(
    <AdvancedSettingsProvider>
      <RemuxTab />
    </AdvancedSettingsProvider>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('RemuxTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Trash Directory label', () => {
    renderTab()
    expect(screen.getByText('Trash Directory')).toBeInTheDocument()
  })

  it('renders Trash Directory input with value from config', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    expect(inputs.some((el) => (el as HTMLInputElement).value === '/media/trash')).toBe(true)
  })

  it('renders Backup Retention days input', () => {
    renderTab()
    expect(screen.getByText('Backup Retention (days)')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    expect(spinners.some((el) => (el as HTMLInputElement).value === '7')).toBe(true)
  })

  it('renders Use Reflink toggle', () => {
    renderTab()
    expect(screen.getByText('Use Reflink')).toBeInTheDocument()
  })

  it('renders Pause Arr on Remux toggle', () => {
    renderTab()
    expect(screen.getByText('Pause Arr on Remux')).toBeInTheDocument()
  })

  it('calls updateConfig on toggle change', () => {
    renderTab()
    const toggles = screen.getAllByRole('switch')
    fireEvent.click(toggles[0])
    expect(mutateMock).toHaveBeenCalled()
  })

  it('calls updateConfig on blur for trash dir', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    const trashInput = inputs.find((el) => (el as HTMLInputElement).value === '/media/trash') as HTMLInputElement
    fireEvent.blur(trashInput)
    expect(mutateMock).toHaveBeenCalled()
  })

  it('previews (dry-run) then confirms remux backup cleanup', async () => {
    cleanupMock.mockResolvedValueOnce({ count: 3, would_delete: ['a', 'b', 'c'] })
    cleanupMock.mockResolvedValueOnce({ deleted: ['a', 'b', 'c'] })
    renderTab()

    fireEvent.click(screen.getByText('Check'))
    // dry-run preview shows the count and a confirm button appears
    expect(await screen.findByText('remux_tab.cleanup_would_delete:3')).toBeInTheDocument()
    expect(cleanupMock).toHaveBeenCalledWith(true)

    fireEvent.click(screen.getByText('Delete now'))
    await waitFor(() => expect(cleanupMock).toHaveBeenCalledWith(false))
  })

  it('shows a "nothing to clean" message when the dry-run count is 0', async () => {
    cleanupMock.mockResolvedValueOnce({ count: 0, would_delete: [] })
    renderTab()
    fireEvent.click(screen.getByText('Check'))
    expect(
      await screen.findByText('No backups older than the retention window.'),
    ).toBeInTheDocument()
  })
})
