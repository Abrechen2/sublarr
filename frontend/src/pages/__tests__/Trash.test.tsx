import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

const batches = Array.from({ length: 30 }, (_, i) => ({
  batch_id: `b${i}`, created_at: null, expires_at: null, file_count: 1, size_bytes: 10,
  series_name: `Series ${i}`, language: 'de', files: [`f${i}.srt`],
}))
const backups = Array.from({ length: 12 }, (_, i) => ({
  path: `/m/${i}.mkv.bak`, video_path: null, size_bytes: 10, mtime: 0, expires_at: null,
}))

const idle = { mutate: vi.fn(), isPending: false }
vi.mock('@/hooks/useTrashApi', () => ({
  useTrashOverview: () => ({
    data: {
      sidecar_batches: batches,
      mkv_backups: backups,
      total_size_bytes: 420,
      retention: { subtitle_trash_days: 30, mkv_backup_days: 7 },
    },
    isLoading: false,
  }),
  useRestoreSidecarBatch: () => idle,
  useDeleteSidecarBatch: () => idle,
  useDeleteMkvBackup: () => idle,
  useRestoreMkvBackup: () => idle,
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

import { TrashPage } from '../Trash'

describe('TrashPage lists', () => {
  // A trash of hundreds of batches scrolled the page for ages; each list now
  // scrolls in its own box and folds away under its header.
  it('puts each list in a scroll box', () => {
    render(<TrashPage />)
    expect(screen.getByTestId('trash-sidecar-list').className).toContain('overflow-y-auto')
    expect(screen.getByTestId('trash-mkv-list').className).toContain('overflow-y-auto')
  })

  it('folds a list under its header', () => {
    render(<TrashPage />)
    fireEvent.click(screen.getByTestId('trash-sidecar-toggle'))
    expect(screen.queryByTestId('trash-sidecar-list')).toBeNull()
    expect(screen.getByTestId('trash-mkv-list')).toBeTruthy()
    fireEvent.click(screen.getByTestId('trash-sidecar-toggle'))
    expect(screen.getByTestId('trash-sidecar-list')).toBeTruthy()
  })
})
