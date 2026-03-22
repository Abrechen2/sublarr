import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, it, expect, describe, beforeEach } from 'vitest'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { ConfigExportImportTab } from '../ConfigExportImportTab'

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
})
