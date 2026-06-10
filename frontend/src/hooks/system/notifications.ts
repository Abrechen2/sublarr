import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import {
  getNotificationTemplates, createNotificationTemplate, updateNotificationTemplate, deleteNotificationTemplate,
  previewNotificationTemplate, getTemplateVariables,
  getQuietHours, createQuietHours, updateQuietHours, deleteQuietHours,
  getNotificationHistory, resendNotification,
  getNotificationFilters, updateNotificationFilters,
} from '@/api/client'
import type {
  NotificationTemplate, QuietHoursConfig, NotificationFilter,
} from '@/lib/types'

// ─── Notification Templates ──────────────────────────────────────────────────

export function useNotificationTemplates() {
  return useQuery({
    queryKey: ['notification-templates'],
    queryFn: getNotificationTemplates,
    staleTime: 30_000,
  })
}

export function useCreateNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (template: Partial<NotificationTemplate>) => createNotificationTemplate(template),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function useUpdateNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<NotificationTemplate> }) =>
      updateNotificationTemplate(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function useDeleteNotificationTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteNotificationTemplate(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-templates'] }) },
  })
}

export function usePreviewNotificationTemplate() {
  return useMutation({
    mutationFn: (id: number) => previewNotificationTemplate(id),
  })
}

export function useTemplateVariables(eventType?: string) {
  return useQuery({
    queryKey: ['template-variables', eventType],
    queryFn: () => getTemplateVariables(eventType),
    staleTime: 60_000,
  })
}

export function useQuietHours() {
  return useQuery({
    queryKey: ['quiet-hours'],
    queryFn: getQuietHours,
    staleTime: 30_000,
  })
}

export function useCreateQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (config: Partial<QuietHoursConfig>) => createQuietHours(config),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useUpdateQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<QuietHoursConfig> }) =>
      updateQuietHours(id, data),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useDeleteQuietHours() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => deleteQuietHours(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['quiet-hours'] }) },
  })
}

export function useNotificationHistory(page = 1, eventType?: string) {
  return useQuery({
    queryKey: ['notification-history', page, eventType],
    queryFn: () => getNotificationHistory(page, eventType),
    staleTime: 15_000,
    placeholderData: keepPreviousData,
  })
}

export function useResendNotification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => resendNotification(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-history'] }) },
  })
}

export function useNotificationFilters() {
  return useQuery({
    queryKey: ['notification-filters'],
    queryFn: getNotificationFilters,
    staleTime: 60_000,
  })
}

export function useUpdateNotificationFilters() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (filters: NotificationFilter) => updateNotificationFilters(filters),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['notification-filters'] }) },
  })
}
