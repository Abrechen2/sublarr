// Scheduler job metadata: friendly name + category mapping.
// The translation key approach lets DE/EN strings live in i18n while we
// keep the categorisation logic here as the single source of truth.
//
// 2026-05-09 redesign: groups jobs into 3 SettingsSections so the page
// is scannable at a glance. Approach B from the redesign brief.

import type { LucideIcon } from 'lucide-react'
import { Search, RefreshCw, Wrench } from 'lucide-react'

export type JobCategory = 'scanning' | 'metadata' | 'maintenance'

export interface JobCategoryDef {
  readonly id: JobCategory
  readonly icon: LucideIcon
  readonly titleKey: string
  readonly descKey: string
}

// Display order on the page.
export const JOB_CATEGORIES: readonly JobCategoryDef[] = [
  {
    id: 'scanning',
    icon: Search,
    titleKey: 'scheduler.category.scanning.title',
    descKey: 'scheduler.category.scanning.desc',
  },
  {
    id: 'metadata',
    icon: RefreshCw,
    titleKey: 'scheduler.category.metadata.title',
    descKey: 'scheduler.category.metadata.desc',
  },
  {
    id: 'maintenance',
    icon: Wrench,
    titleKey: 'scheduler.category.maintenance.title',
    descKey: 'scheduler.category.maintenance.desc',
  },
] as const

// Static job → category map. New jobs default to 'maintenance' so they
// show up somewhere visible until explicitly classified here.
const JOB_CATEGORY: Record<string, JobCategory> = {
  wanted_scanner: 'scanning',
  wanted_search: 'scanning',
  upgrade_scan: 'scanning',
  standalone_scan: 'scanning',
  subtitle_automation: 'scanning',
  anidb_sync: 'metadata',
  cleanup: 'maintenance',
  scheduler_history_cleanup: 'maintenance',
  translation_events_cleanup: 'maintenance',
}

export function categorize(jobId: string): JobCategory {
  return JOB_CATEGORY[jobId] ?? 'maintenance'
}

// Translation key for a per-job friendly name + tagline. The fallback
// (defaultValue) keeps the page readable when a string hasn't been
// translated yet.
export function jobNameKey(jobId: string): string {
  return `scheduler.jobs.${jobId}.name`
}

export function jobDescKey(jobId: string): string {
  return `scheduler.jobs.${jobId}.desc`
}
