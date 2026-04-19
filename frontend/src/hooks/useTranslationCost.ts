import { useQuery } from '@tanstack/react-query'
import {
  getConcurrency,
  getCostByBackend,
  getCostSummary,
  getMemoryTelemetry,
} from '@/api/translation'

/**
 * Phase A1 translation telemetry hooks.
 *
 * Dashboard-style cost and memory data poll every 30 s; concurrency polls
 * every 10 s because the operator may adjust it interactively and wants
 * immediate feedback.
 */

export function useTranslationCostSummary() {
  return useQuery({
    queryKey: ['translation', 'cost', 'summary'],
    queryFn: getCostSummary,
    refetchInterval: 30000,
  })
}

export function useTranslationCostByBackend(
  window: '7d' | '30d' | 'today' = '7d',
) {
  return useQuery({
    queryKey: ['translation', 'cost', 'by-backend', window],
    queryFn: () => getCostByBackend(window),
    refetchInterval: 30000,
  })
}

/**
 * A1 memory telemetry (rows, size_bytes, hit_rate_7d) from
 * `/translation/memory/stats`. Distinct from `useTranslationMemoryStats`
 * in `useTranslationApi.ts` which hits the legacy `/translation-memory/stats`.
 */
export function useTranslationMemoryTelemetry() {
  return useQuery({
    queryKey: ['translation', 'memory', 'stats'],
    queryFn: getMemoryTelemetry,
    refetchInterval: 30000,
  })
}

export function useTranslationConcurrency() {
  return useQuery({
    queryKey: ['translation', 'concurrency'],
    queryFn: getConcurrency,
    refetchInterval: 10000,
  })
}
