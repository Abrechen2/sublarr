import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getTrashOverview,
  restoreSidecarBatch,
  deleteSidecarBatch,
  deleteMkvBackup,
  restoreMkvBackup,
} from '@/api/trash'
import { toast } from '@/components/shared/Toast'
import i18n from '@/i18n'

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
      toast(i18n.t('common:trash.toast.restored', { count: result.restored }))
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast(i18n.t('common:trash.toast.restore_failed'), 'error'),
  })
}

export function useDeleteSidecarBatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (batchId: string) => deleteSidecarBatch(batchId),
    onSuccess: () => {
      toast(i18n.t('common:trash.toast.batch_deleted'))
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast(i18n.t('common:trash.toast.delete_failed'), 'error'),
  })
}

export function useDeleteMkvBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (backupPath: string) => deleteMkvBackup(backupPath),
    onSuccess: () => {
      toast(i18n.t('common:trash.toast.backup_deleted'))
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast(i18n.t('common:trash.toast.delete_failed'), 'error'),
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
          ? i18n.t('common:trash.toast.video_restored_with_sidecars', { count: result.sidecars_deleted })
          : i18n.t('common:trash.toast.video_restored')
      toast(msg)
      qc.invalidateQueries({ queryKey: TRASH_KEY })
    },
    onError: () => toast(i18n.t('common:trash.toast.restore_failed'), 'error'),
  })
}
