import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getTrashOverview,
  restoreSidecarBatch,
  deleteSidecarBatch,
  deleteMkvBackup,
  restoreMkvBackup,
} from '@/api/trash'
import { toast } from '@/components/shared/Toast'

const TRASH_KEY = ['trash']

export function useTrashOverview() {
  return useQuery({
    queryKey: TRASH_KEY,
    queryFn: getTrashOverview,
    staleTime: 30_000,
  })
}

export function useRestoreSidecarBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (batchId: string) => restoreSidecarBatch(batchId),
    onSuccess: (result) => {
      toast(`${result.restored} Untertitel wiederhergestellt`)
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast('Wiederherstellung fehlgeschlagen', 'error'),
  })
}

export function useDeleteSidecarBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (batchId: string) => deleteSidecarBatch(batchId),
    onSuccess: () => {
      toast('Batch endgÃ¼ltig gelÃ¶scht')
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast('LÃ¶schen fehlgeschlagen', 'error'),
  })
}

export function useDeleteMkvBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (backupPath: string) => deleteMkvBackup(backupPath),
    onSuccess: () => {
      toast('Backup endgÃ¼ltig gelÃ¶scht')
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast('LÃ¶schen fehlgeschlagen', 'error'),
  })
}

export function useRestoreMkvBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      backupPath,
      videoPath,
      deleteSidecars,
    }: {
      backupPath: string
      videoPath: string
      deleteSidecars: boolean
    }) => restoreMkvBackup(backupPath, videoPath, deleteSidecars),
    onSuccess: (result) => {
      const msg =
        result.sidecars_deleted > 0
          ? `Video wiederhergestellt â€” ${result.sidecars_deleted} Sidecar-Batch(es) gelÃ¶scht`
          : 'Video-Backup wiederhergestellt'
      toast(msg)
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast('Wiederherstellung fehlgeschlagen', 'error'),
  })
}
