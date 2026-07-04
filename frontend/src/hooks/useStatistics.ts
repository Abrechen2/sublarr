/** React Query hooks for the grouped analytics API (V1.6 #9). */
import { useQuery } from '@tanstack/react-query'
import {
  getSubtitlesStats,
  getTranslationStats,
  getProvidersStats,
  getSystemStats,
  getLibraryStats,
  getTrendsStats,
  type StatRange,
} from '@/api/client'

const STALE = 60_000

export function useStatSubtitles(range: StatRange) {
  return useQuery({ queryKey: ['stats', 'subtitles', range], queryFn: () => getSubtitlesStats(range), staleTime: STALE })
}
export function useStatTranslation(range: StatRange) {
  return useQuery({ queryKey: ['stats', 'translation', range], queryFn: () => getTranslationStats(range), staleTime: STALE })
}
export function useStatProviders() {
  return useQuery({ queryKey: ['stats', 'providers'], queryFn: getProvidersStats, staleTime: STALE })
}
export function useStatSystem() {
  return useQuery({ queryKey: ['stats', 'system'], queryFn: getSystemStats, staleTime: 30_000, refetchInterval: 30_000 })
}
export function useStatLibrary() {
  return useQuery({ queryKey: ['stats', 'library'], queryFn: getLibraryStats, staleTime: STALE })
}
export function useStatTrends(range: StatRange) {
  return useQuery({ queryKey: ['stats', 'trends', range], queryFn: () => getTrendsStats(range), staleTime: STALE })
}
