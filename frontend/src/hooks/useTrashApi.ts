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
      toast.success(`${result.restored} Untertitel wiederhergestellt`)
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast.error('Wiederherstellung fehlgeschlagen'),
  })
}

export function useDeleteSidecarBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (batchId: string) => deleteSidecarBatch(batchId),
    onSuccess: () => {
      toast.success('Batch endgültig gelöscht')
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast.error('Löschen fehlgeschlagen'),
  })
}

export function useDeleteMkvBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (backupPath: string) => deleteMkvBackup(backupPath),
    onSuccess: () => {
      toast.success('Backup endgültig gelöscht')
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast.error('Löschen fehlgeschlagen'),
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
          ? `Video wiederhergestellt — ${result.sidecars_deleted} Sidecar-Batch(es) gelöscht`
          : 'Video-Backup wiederhergestellt'
      toast.success(msg)
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast.error('Wiederherstellung fehlgeschlagen'),
  })
}
