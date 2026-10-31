import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, it, expect, describe, beforeEach } from 'vitest'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { ConfigExportImportTab } from '../ConfigExportImportTab'
import { toast } from '@/components/shared/Toast'

const mockExport = vi.fn()
const mockImport = vi.fn()

vi.mock('@/hooks/useSystemApi', () => ({
  useExportConfig: () => ({ mutate: mockExport, isPending: false }),
  useImportConfig: () => ({ mutate: mockImport, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: vi.fn() }))

function renderTab() {
  return render(
    <AdvancedSettingsProvider>
      <ConfigExportImportTab />
    </AdvancedSettingsProvider>,
  )
}

describe('ConfigExportImportTab', () => {
  beforeEach(() => {
    mockExport.mockClear()
    mockImport.mockClear()
  })

  it('renders export button', () => {
    renderTab()
    expect(screen.getByTestId('export-config-btn')).toBeInTheDocument()
  })

  it('renders file input for import', () => {
    renderTab()
    expect(screen.getByTestId('import-file-input')).toBeInTheDocument()
  })

  it('calls export mutate on export button click', () => {
    renderTab()
    fireEvent.click(screen.getByTestId('export-config-btn'))
    expect(mockExport).toHaveBeenCalled()
  })

  it('shows confirm dialog before import', async () => {
    renderTab()
    const file = new File(['{"key":"val"}'], 'config.json', { type: 'application/json' })
    fireEvent.change(screen.getByTestId('import-file-input'), {
      target: { files: [file] },
    })
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
  })

  // Audit #61 A30: refused keys vanished, and an import error said "Export failed".
  async function confirmImport() {
    renderTab()
    const file = new File(['{"items_per_page":1}'], 'config.json', { type: 'application/json' })
    fireEvent.change(screen.getByTestId('import-file-input'), { target: { files: [file] } })
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('import-confirm-btn'))
    return mockImport.mock.calls[0][1] as {
      onSuccess: (r: unknown) => void
      onError: (e: unknown) => void
    }
  }

  it('names the settings the server refused', async () => {
    const { onSuccess } = await confirmImport()
    onSuccess({
      status: 'imported',
      imported_keys: [],
      skipped_secrets: [],
      skipped_invalid: [{ key: 'items_per_page', error: 'items_per_page must be an integer between 10 and 200' }],
    })
    expect(vi.mocked(toast)).toHaveBeenCalledWith(
      expect.stringContaining('items_per_page must be an integer'),
      'error',
    )
  })

  it('shows the server reason when the import fails', async () => {
    const { onError } = await confirmImport()
    onError({ response: { data: { error: 'Import payload must be a JSON object' } } })
    expect(vi.mocked(toast)).toHaveBeenCalledWith('Import payload must be a JSON object', 'error')
  })
})
