import { render, screen, fireEvent } from '@testing-library/react'
import { vi, it, expect, describe, beforeEach } from 'vitest'
import { MigrationTab } from '../MigrationTab'
import type { BazarrMigrationPreview, BazarrMigrationResult } from '@/lib/types'

const analyzeMutate = vi.fn()
const confirmMutate = vi.fn()
const toastMock = vi.fn()

vi.mock('@/hooks/useIntegrationApi', () => ({
  useBazarrMigration: () => ({ mutate: analyzeMutate, isPending: false }),
  useConfirmBazarrImport: () => ({ mutate: confirmMutate, isPending: false }),
}))

vi.mock('@/components/shared/Toast', () => ({ toast: (...a: unknown[]) => toastMock(...a) }))

const PREVIEW: BazarrMigrationPreview = {
  status: 'preview',
  config_entries: [
    { key: 'sonarr_url', value: 'http://10.0.0.5:8989/sonarr', current_value: 'http://old:8989', source: 'Bazarr config (sonarr)' },
    { key: 'sonarr_api_key', value: 'abcd***', current_value: '', source: 'Bazarr config (sonarr)' },
  ],
  profiles: [{ name: 'Deutsch', languages: ['de'] }],
  blacklist_count: 3,
  warnings: [],
}

const RESULT: BazarrMigrationResult = {
  status: 'applied',
  config_imported: 2,
  profiles_imported: 1,
  blacklist_imported: 3,
  saved_keys: ['sonarr_url', 'sonarr_api_key'],
  warnings: ['radarr_url not imported: loopback'],
}

const configFile = new File(['sonarr: {}'], 'config.yaml')
const dbFile = new File(['SQLite format 3'], 'bazarr.db')

function pickFiles() {
  fireEvent.change(screen.getByTestId('bazarr-config-input'), { target: { files: [configFile] } })
  fireEvent.change(screen.getByTestId('bazarr-db-input'), { target: { files: [dbFile] } })
}

type Callbacks<T> = { onSuccess?: (d: T) => void; onError?: (e: unknown) => void }

describe('MigrationTab', () => {
  beforeEach(() => {
    analyzeMutate.mockReset()
    confirmMutate.mockReset()
    toastMock.mockReset()
  })

  it('sends the chosen files to the server instead of simulating a preview', () => {
    render(<MigrationTab />)
    pickFiles()
    fireEvent.click(screen.getByTestId('bazarr-analyze'))
    expect(analyzeMutate).toHaveBeenCalledWith([configFile, dbFile], expect.anything())
  })

  it('shows the server preview, including what each entry would overwrite', () => {
    analyzeMutate.mockImplementation((_f: File[], cb: Callbacks<BazarrMigrationPreview>) => cb.onSuccess?.(PREVIEW))
    render(<MigrationTab />)
    pickFiles()
    fireEvent.click(screen.getByTestId('bazarr-analyze'))

    expect(screen.getByTestId('bazarr-entry-sonarr_url')).toHaveTextContent('http://10.0.0.5:8989/sonarr')
    expect(screen.getByTestId('bazarr-entry-sonarr_url')).toHaveTextContent('http://old:8989')
    expect(screen.getByText('Deutsch')).toBeInTheDocument()
  })

  it('confirms with the same files and reports what the server imported', () => {
    analyzeMutate.mockImplementation((_f: File[], cb: Callbacks<BazarrMigrationPreview>) => cb.onSuccess?.(PREVIEW))
    confirmMutate.mockImplementation((_f: File[], cb: Callbacks<BazarrMigrationResult>) => cb.onSuccess?.(RESULT))
    render(<MigrationTab />)
    pickFiles()
    fireEvent.click(screen.getByTestId('bazarr-analyze'))
    fireEvent.click(screen.getByTestId('bazarr-confirm'))

    expect(confirmMutate).toHaveBeenCalledWith([configFile, dbFile], expect.anything())
    const result = screen.getByTestId('bazarr-result')
    expect(result).toHaveTextContent('2')
    expect(result).toHaveTextContent('radarr_url not imported: loopback')
  })

  it('shows the server error and its warnings when nothing can be imported', () => {
    analyzeMutate.mockImplementation((_f: File[], cb: Callbacks<BazarrMigrationPreview>) =>
      cb.onError?.({ response: { data: { error: 'No importable Bazarr settings found', warnings: ['Empty config file'] } } }),
    )
    render(<MigrationTab />)
    pickFiles()
    fireEvent.click(screen.getByTestId('bazarr-analyze'))

    expect(toastMock).toHaveBeenCalledWith('No importable Bazarr settings found', 'error')
    expect(screen.getByTestId('bazarr-warnings')).toHaveTextContent('Empty config file')
  })
})
