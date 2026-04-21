import { useQuery } from '@tanstack/react-query'

import { fetchSyncEngines, fetchSyncRuns } from '@/api/syncEngines'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { useTranslation } from 'react-i18next'

// Plan B7 — Multi-Engine Sync Orchestrator settings tab.
//
// Informational view: shows the configured engine chain, each engine's
// availability, the sanity threshold, and the recent sync_job_runs audit
// rows. Chain editing is a follow-up — B7 ships the architecture.

function LoadingState() {
  const { t } = useTranslation('common')
  return <div className="py-8 text-center text-muted">{t('sync_engines_tab.loading')}</div>
}

function ErrorState({ message }: { readonly message: string }) {
  return (
    <div className="py-8 text-center" style={{ color: 'var(--error)' }}>
      {message}
    </div>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function formatOffset(ms: number | null): string {
  if (ms === null || ms === undefined) return '—'
  return `${ms} ms`
}

export function SyncEnginesTab() {
  const { t } = useTranslation('settings')
  const enginesQuery = useQuery({
    queryKey: ['sync-engines', 'engines'],
    queryFn: fetchSyncEngines,
  })
  const runsQuery = useQuery({
    queryKey: ['sync-engines', 'runs'],
    queryFn: () => fetchSyncRuns(50),
  })

  if (enginesQuery.isLoading) {
    return (
      <SettingsDetailLayout title={t('sync_engines_tab.title')}>
        <LoadingState />
      </SettingsDetailLayout>
    )
  }
  if (enginesQuery.isError) {
    return (
      <SettingsDetailLayout title={t('sync_engines_tab.title')}>
        <ErrorState message="Error loading sync engine configuration." />
      </SettingsDetailLayout>
    )
  }

  const engines = enginesQuery.data?.engines ?? []
  const sanityMs = enginesQuery.data?.sanity_threshold_ms ?? 0
  const runs = runsQuery.data ?? []

  return (
    <SettingsDetailLayout
      title={t('sync_engines_tab.title')}
      subtitle="Ordered fallback chain for subtitle synchronization. The orchestrator tries each engine in turn and accepts the first sane result."
    >
      <div className="max-w-3xl space-y-6">
        <section className="bg-surface border border-border rounded-md p-4">
          <h2 className="font-medium mb-3">{t('sync_engines_tab.engine_chain')}</h2>
          {engines.length === 0 ? (
            <p className="text-muted text-sm">{t('sync_engines_tab.no_engines')}</p>
          ) : (
            <ol className="space-y-2">
              {engines.map((engine, idx) => (
                <li
                  key={engine.name}
                  className="flex items-center gap-3 bg-bg rounded-md p-3 border border-border"
                >
                  <span className="text-xs text-muted">{idx + 1}.</span>
                  <code className="text-sm flex-1">{engine.name}</code>
                  <span
                    className="text-xs px-2 py-1 rounded border"
                    style={{
                      color: engine.available ? 'var(--success)' : 'var(--error)',
                      borderColor: engine.available ? 'var(--success)' : 'var(--error)',
                    }}
                  >
                    {engine.available ? 'available' : 'unavailable'}
                  </span>
                  <span className="text-xs text-muted hidden md:inline">
                    timeout {engine.timeout_s}s
                  </span>
                </li>
              ))}
            </ol>
          )}
          <p className="text-xs text-muted mt-3">
            Sanity threshold:{' '}
            <code>{sanityMs} ms</code>. Engines whose computed offset exceeds this limit
            are rejected and the next engine in the chain is tried.
          </p>
        </section>

        <section className="bg-surface border border-border rounded-md p-4">
          <h2 className="font-medium mb-3">{t('sync_engines_tab.recent_runs')}</h2>
          {runsQuery.isLoading ? (
            <p className="text-muted text-sm">{t('sync_engines_tab.loading_runs')}</p>
          ) : runs.length === 0 ? (
            <p className="text-muted text-sm">
              No sync runs recorded yet. Every engine attempt (success, skip, error)
              will appear here.
            </p>
          ) : (
            <ul className="space-y-2">
              {runs.map((run) => (
                <li
                  key={run.id}
                  className="bg-bg rounded-md p-3 border border-border text-sm"
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <code className="text-sm">{run.engine}</code>
                    <span className="text-xs px-2 py-0.5 rounded bg-surface border border-border">
                      {run.status}
                    </span>
                    <span className="text-xs text-muted">
                      offset {formatOffset(run.offset_ms)} · {run.duration_ms} ms ·{' '}
                      {formatDate(run.created_at)}
                    </span>
                  </div>
                  {run.reason && (
                    <p className="text-xs text-muted mt-1">reason: {run.reason}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </SettingsDetailLayout>
  )
}
