/**
 * BackupRetentionFields.test.tsx — Tests for backup retention config fields in BackupTab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BackupTab } from '../AdvancedTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mutateMock = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useFullBackups: () => ({ data: { backups: [] }, isLoading: false }),
  useCreateFullBackup: () => ({ mutate: vi.fn(), isPending: false }),
  useRestoreFullBackup: () => ({ mutate: vi.fn(), isPending: false }),
  useConfig: () => ({
    data: {
      backup_dir: '/config/backups',
      backup_retention_daily: '7',
      backup_retention_weekly: '4',
      backup_retention_monthly: '3',
    },
  }),
  useUpdateConfig: () => ({ mutate: mutateMock, isPending: false }),
}))

vi.mock('@/api/client', () => ({
  downloadFullBackupUrl: (filename: string) => `/api/v1/backups/download/${filename}`,
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('BackupTab — Retention Policy fields', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderTab = () =>
    render(
      <AdvancedSettingsProvider>
        <BackupTab />
      </AdvancedSettingsProvider>,
    )

  it('renders the Retention Policy heading', () => {
    renderTab()
    expect(screen.getByText('Retention Policy')).toBeInTheDocument()
  })

  it('renders Backup Directory label', () => {
    renderTab()
    expect(screen.getByText('Backup Directory')).toBeInTheDocument()
  })

  it('renders Backup Directory input with value from config', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    const dirInput = inputs.find((el) => (el as HTMLInputElement).value === '/config/backups')
    expect(dirInput).toBeDefined()
  })

  it('renders Daily Backups number input with value from config', () => {
    renderTab()
    expect(screen.getByText('Daily Backups')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    const daily = spinners.find((el) => (el as HTMLInputElement).value === '7')
    expect(daily).toBeDefined()
  })

  it('renders Weekly Backups number input with value from config', () => {
    renderTab()
    expect(screen.getByText('Weekly Backups')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    const weekly = spinners.find((el) => (el as HTMLInputElement).value === '4')
    expect(weekly).toBeDefined()
  })

  it('renders Monthly Backups number input with value from config', () => {
    renderTab()
    expect(screen.getByText('Monthly Backups')).toBeInTheDocument()
    const spinners = screen.getAllByRole('spinbutton')
    const monthly = spinners.find((el) => (el as HTMLInputElement).value === '3')
    expect(monthly).toBeDefined()
  })

  it('calls updateConfig on blur for backup_dir', () => {
    renderTab()
    const inputs = screen.getAllByRole('textbox')
    const dirInput = inputs.find((el) => (el as HTMLInputElement).value === '/config/backups') as HTMLInputElement
    fireEvent.blur(dirInput)
    // blur on the dir field triggers mutate (initial value from config)
    expect(mutateMock).toHaveBeenCalled()
  })

  it('calls updateConfig on blur for backup_retention_daily', () => {
    renderTab()
    const spinners = screen.getAllByRole('spinbutton')
    const daily = spinners.find((el) => (el as HTMLInputElement).value === '7') as HTMLInputElement
    fireEvent.blur(daily)
    // blur on the daily field triggers mutate
    expect(mutateMock).toHaveBeenCalled()
  })
})
