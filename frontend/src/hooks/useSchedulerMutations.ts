import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  modifyTrigger,
  pauseJob,
  resetDefault,
  resumeJob,
  runNow,
} from '@/api/scheduler'
import type { Trigger } from '@/lib/types'

export function useSchedulerMutations(jobId: string) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['scheduler', 'jobs'] })
    qc.invalidateQueries({ queryKey: ['scheduler', 'jobs', jobId] })
  }

  return {
    runNow: useMutation({
      mutationFn: () => runNow(jobId),
      onSuccess: invalidate,
    }),
    pause: useMutation({
      mutationFn: () => pauseJob(jobId),
      onSuccess: invalidate,
    }),
    resume: useMutation({
      mutationFn: () => resumeJob(jobId),
      onSuccess: invalidate,
    }),
    patchTrigger: useMutation({
      mutationFn: (trigger: Trigger) => modifyTrigger(jobId, trigger),
      onSuccess: invalidate,
    }),
    resetDefault: useMutation({
      mutationFn: () => resetDefault(jobId),
      onSuccess: invalidate,
    }),
  }
}
