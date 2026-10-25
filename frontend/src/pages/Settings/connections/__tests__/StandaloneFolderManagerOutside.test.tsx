/**
 * A watched folder outside the media folder is flagged, and a refused add
 * shows the server's reason instead of a generic failure.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { StandaloneFolderManager } from '../StandaloneFolderManager'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const toastMock = vi.fn()
vi.mock('@/components/shared/Toast', () => ({ toast: (...args: unknown[]) => toastMock(...args) }))

const FOLDERS = {
  data: [
    { id: 1, path: '/media/anime', label: '', media_type: 'auto', enabled: true, last_scan_at: '', created_at: '', updated_at: '', outside_media_path: false },
    { id: 2, path: '/data/other', label: '', media_type: 'auto', enabled: true, last_scan_at: '', created_at: '', updated_at: '', outside_media_path: true },
  ],
  isLoading: false,
}
const CONFIG = { data: { standalone_enabled: true } }
const REFUSAL = { response: { data: { error: '/data/other is outside the media folder /media.' } } }
const saveMutate = vi.fn((_vars: unknown, opts: { onError?: (e: unknown) => void }) => opts.onError?.(REFUSAL))

vi.mock('@/hooks/useApi', () => ({
  useWatchedFolders: () => FOLDERS,
  useSaveWatchedFolder: () => ({ mutate: saveMutate, isPending: false }),
  useDeleteWatchedFolder: () => ({ mutate: vi.fn(), isPending: false }),
  useTriggerStandaloneFolderScan: () => ({ mutate: vi.fn(), isPending: false }),
  useStandaloneStatus: () => ({ data: { auto_activated: false } }),
  useConfig: () => CONFIG,
  useUpdateConfig: () => ({ mutate: vi.fn(), isPending: false }),
}))

describe('StandaloneFolderManager outside the media folder', () => {
  beforeEach(() => {
    toastMock.mockClear()
    saveMutate.mockClear()
  })

  it('flags only the folder outside the media folder', () => {
    render(<StandaloneFolderManager />)
    expect(screen.getByTestId('folder-outside-media-2')).toHaveTextContent('library_sources.outside_media_path')
    expect(screen.queryByTestId('folder-outside-media-1')).toBeNull()
  })

  it("shows the server's reason when adding is refused", () => {
    render(<StandaloneFolderManager />)
    fireEvent.click(screen.getByText('library_sources.add_folder'))
    fireEvent.change(screen.getByPlaceholderText('/path/to/media'), { target: { value: '/data/other' } })
    fireEvent.click(screen.getByText('library_sources_tab.save'))
    expect(saveMutate).toHaveBeenCalled()
    expect(toastMock).toHaveBeenCalledWith('/data/other is outside the media folder /media.', 'error')
  })
})
