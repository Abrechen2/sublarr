/**
 * BackupManagement.test.tsx — Tests for backup management UI in BackupTab.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BackupTab } from '../AdvancedTab'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// ─── Mocks ───────────────────────────────────────────────────────────────────

const createMutate = vi.fn()
const restoreMutate = vi.fn()

vi.mock('@/hooks/useApi', () => ({
  useFullBackups: () => ({
    data: {
      backups: [
        { filename: 'backup-2024-01-01.zip', size_bytes: 1024000, created_at: '2024-01-01T00:00:00Z' },
        { filename: 'backup-2024-01-02.zip', size_bytes: 2048000, created_at: '2024-01-02T00:00:00Z' },
      ],
    },
    isLoading: false,
  }),
  useCreateFullBackup: () => ({ mutate: createMutate, isPending: false }),
  useRestoreFullBackup: () => ({ mutate: restoreMutate, isPending: false }),
  useConfig: () => ({ data: {} }),
  useUpdateConfig: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/api/client', () => ({
  downloadFullBackupUrl: (filename: string) => `/api/v1/backups/download/${filename}`,
}))

vi.mock('@/components/shared/Toast', () => ({
  toast: vi.fn(),
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderTab() {
  return render(
    <AdvancedSettingsProvider>
      <BackupTab />
    </AdvancedSettingsProvider>,
  )
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('BackupTab — Backup Management UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Create Backup button', () => {
    renderTab()
    expect(screen.getByText('Create Backup')).toBeInTheDocument()
  })

  it('calls createBackup.mutate when Create Backup is clicked', () => {
    renderTab()
    const btn = screen.getByText('Create Backup')
    fireEvent.click(btn)
    expect(createMutate).toHaveBeenCalled()
  })

  it('renders the list of existing backups', () => {
    renderTab()
    expect(screen.getByText('backup-2024-01-01.zip')).toBeInTheDocument()
    expect(screen.getByText('backup-2024-01-02.zip')).toBeInTheDocument()
  })

  it('renders Download links for each backup', () => {
    renderTab()
    const downloadLinks = screen.getAllByText('Download')
    expect(downloadLinks).toHaveLength(2)
  })

  it('download links have correct href', () => {
    renderTab()
    const downloadLinks = screen.getAllByRole('link', { name: /download/i })
    expect(downloadLinks[0]).toHaveAttribute(
      'href',
      '/api/v1/backups/download/backup-2024-01-01.zip',
    )
  })

  it('renders Restore from File section', () => {
    renderTab()
    expect(screen.getByText('Restore from File')).toBeInTheDocument()
  })

  it('renders Select ZIP File button', () => {
    renderTab()
    expect(screen.getByText('Select ZIP File')).toBeInTheDocument()
  })
})
