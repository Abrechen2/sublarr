/**
 * IntegrationsTab -- Settings tab for external integration features.
 *
 * Four collapsible sections:
 * 1. Bazarr Migration -- mapping report from a Bazarr DB path
 * 2. Compatibility Check -- Plex/Kodi subtitle naming validation
 * 3. Extended Health Diagnostics -- structured service diagnostics
 * 4. Export Configuration -- multi-format config export + ZIP bundle
 */
import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ChevronDown, ChevronRight, FileJson, Shield, Heart, Download,
  CheckCircle, XCircle, AlertTriangle, Loader2,
} from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  useBazarrMappingReport, useCompatCheck, useExtendedHealthAll,
  useExportIntegrationConfig, useExportIntegrationConfigZip,
} from '@/hooks/useApi'
import type {
  BazarrMappingReport, CompatBatchResult, ExtendedHealthAllResponse, ExtendedHealthCheck, ExportResult,
} from '@/lib/types'

// ─── Section Wrapper ────────────────────────────────────────────────────────

function Section({ title, icon, children, defaultOpen = true }: {
  title: string
  icon: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left"
        style={{ color: 'var(--text-primary)' }}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span style={{ color: 'var(--accent)' }}>{icon}</span>
        <h3 className="text-sm font-semibold">{title}</h3>
      </button>
      {open && <div className="px-4 pb-4 space-y-4">{children}</div>}
    </div>
  )
}

// ─── Bazarr Migration Section ───────────────────────────────────────────────

function BazarrMigrationSection() {
  const { t } = useTranslation('settings')
  const [dbPath, setDbPath] = useState('')
  const mappingReport = useBazarrMappingReport()
  const [report, setReport] = useState<BazarrMappingReport | null>(null)
  const [tablesExpanded, setTablesExpanded] = useState(false)

  const handleGenerate = useCallback(() => {
    if (!dbPath.trim()) {
      toast(t('integrations.bazarr.dbPathHelp'), 'error')
      return
    }
    mappingReport.mutate(dbPath.trim(), {
      onSuccess: (data) => {
        setReport(data)
        toast(t('integrations.bazarr.reportTitle'))
      },
      onError: () => toast('Failed to generate mapping report', 'error'),
    })
  }, [dbPath, mappingReport, t])

  return (
    <>
      {/* DB Path Input */}
      <div className="space-y-1.5">
        <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {t('integrations.bazarr.dbPath')}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={dbPath}
            onChange={(e) => setDbPath(e.target.value)}
            placeholder="/config/bazarr.db"
            className="flex-1 px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
          />
          <button
            onClick={handleGenerate}
            disabled={mappingReport.isPending || !dbPath.trim()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white"
            style={{ backgroundColor: 'var(--accent)', opacity: mappingReport.isPending || !dbPath.trim() ? 0.5 : 1 }}
          >
            {mappingReport.isPending ? <Loader2 size={14} className="animate-spin" /> : <FileJson size={14} />}
            {t('integrations.bazarr.generateReport')}
          </button>
        </div>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('integrations.bazarr.dbPathHelp')}
        </p>
      </div>

      {/* Report Display */}
      {report && (
        <div className="space-y-4">
          {/* Compatibility */}
          <div className="rounded-md p-3" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
            <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
              {t('integrations.bazarr.compatibility')}
            </h4>
            <div className="grid grid-cols-2 gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <div>
                Bazarr Version:{' '}
                <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {report.compatibility.bazarr_version || 'Unknown'}
                </span>
              </div>
              <div>
                Schema Version:{' '}
                <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {report.compatibility.schema_version || 'Unknown'}
                </span>
              </div>
            </div>
          </div>

          {/* Migration Summary */}
          <div className="rounded-md p-3" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
            <h4 className="text-xs font-semibold mb-2" style={{ color: 'var(--text-secondary)' }}>
              {t('integrations.bazarr.summary')}
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {([
                ['Profiles', report.migration_summary.profiles_count],
                ['Blacklist', report.migration_summary.blacklist_count],
                ['Shows', report.migration_summary.shows_count],
                ['Movies', report.migration_summary.movies_count],
                ['History', report.migration_summary.history_count],
              ] as const).map(([label, count]) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span style={{ color: 'var(--text-muted)' }}>{label}:</span>
                  <span className="font-medium" style={{ color: 'var(--accent)' }}>{count}</span>
                </div>
              ))}
              <div className="flex items-center gap-1.5">
                <span style={{ color: 'var(--text-muted)' }}>Sonarr Config:</span>
                {report.migration_summary.has_sonarr_config ? (
                  <CheckCircle size={12} style={{ color: 'var(--success)' }} />
                ) : (
                  <XCircle size={12} style={{ color: 'var(--text-muted)' }} />
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <span style={{ color: 'var(--text-muted)' }}>Radarr Config:</span>
                {report.migration_summary.has_radarr_config ? (
                  <CheckCircle size={12} style={{ color: 'var(--success)' }} />
                ) : (
                  <XCircle size={12} style={{ color: 'var(--text-muted)' }} />
                )}
              </div>
            </div>
          </div>

          {/* Tables Inventory (Collapsible) */}
          <div className="rounded-md" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
            <button
              onClick={() => setTablesExpanded(!tablesExpanded)}
              className="w-full flex items-center gap-2 px-3 py-2 text-left"
              style={{ color: 'var(--text-secondary)' }}
            >
              {tablesExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              <span className="text-xs font-semibold">
                {t('integrations.bazarr.tables')} ({report.tables_found.length})
              </span>
            </button>
            {tablesExpanded && (
              <div className="px-3 pb-3 space-y-1">
                {report.tables_found.map((table) => {
                  const detail = report.table_details[table]
                  return (
                    <div key={table} className="flex items-center justify-between text-xs py-1"
                      style={{ borderBottom: '1px solid var(--border)' }}
                    >
                      <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{table}</span>
                      <span style={{ color: 'var(--text-muted)' }}>
                        {detail ? `${detail.row_count} rows, ${detail.columns.length} cols` : 'N/A'}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Warnings */}
          {report.warnings.length > 0 && (
            <div className="space-y-1">
              {report.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-xs" style={{ color: 'var(--warning)' }}>
                  <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {/* Link to Import */}
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {t('integrations.bazarr.proceedToImport')}: Settings &gt; API Keys &gt; Bazarr Migration
          </p>
        </div>
      )}
    </>
  )
}

// ─── Compatibility Check Section ────────────────────────────────────────────

function CompatCheckSection() {
  const { t } = useTranslation('settings')
  const [target, setTarget] = useState<'plex' | 'kodi'>('plex')
  const [videoPath, setVideoPath] = useState('')
  const [subtitlePathsText, setSubtitlePathsText] = useState('')
  const compatCheck = useCompatCheck()
  const [results, setResults] = useState<CompatBatchResult | null>(null)

  const handleRun = useCallback(() => {
    const paths = subtitlePathsText.split('\n').map(p => p.trim()).filter(Boolean)
    if (paths.length === 0) {
      toast('Enter at least one subtitle file path', 'error')
      return
    }
    compatCheck.mutate({ subtitlePaths: paths, videoPath: videoPath.trim(), target }, {
      onSuccess: (data) => setResults(data),
      onError: () => toast('Compatibility check failed', 'error'),
    })
  }, [subtitlePathsText, videoPath, target, compatCheck])

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  }

  return (
    <>
      {/* Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('integrations.compat.target')}
          </label>
          <select
            value={target}
            onChange={(e) => setTarget(e.target.value as 'plex' | 'kodi')}
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={inputStyle}
          >
            <option value="plex">Plex</option>
            <option value="kodi">Kodi</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('integrations.compat.videoPath')}
          </label>
          <input
            type="text"
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
            placeholder="/media/anime/Series S01E01.mkv"
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={inputStyle}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {t('integrations.compat.subtitlePaths')}
        </label>
        <textarea
          value={subtitlePathsText}
          onChange={(e) => setSubtitlePathsText(e.target.value)}
          placeholder="/media/anime/Series S01E01.en.ass&#10;/media/anime/Series S01E01.de.srt"
          rows={4}
          className="w-full px-3 py-2 rounded-md text-sm focus:outline-none resize-y"
          style={inputStyle}
        />
      </div>

      <button
        onClick={handleRun}
        disabled={compatCheck.isPending}
        className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white"
        style={{ backgroundColor: 'var(--accent)', opacity: compatCheck.isPending ? 0.5 : 1 }}
      >
        {compatCheck.isPending ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
        {t('integrations.compat.runCheck')}
      </button>

      {/* Results */}
      {results && (
        <div className="space-y-3">
          {/* Summary Bar */}
          <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            <span style={{ color: 'var(--success)' }}>{results.summary.compatible}</span>
            <span>/</span>
            <span>{results.summary.total}</span>
            <span style={{ color: 'var(--text-muted)' }}>{t('integrations.compat.compatible')}</span>
          </div>

          {/* Result Cards */}
          {results.results.map((r, i) => (
            <div
              key={i}
              className="rounded-md p-3 space-y-2"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-2">
                {r.compatible ? (
                  <CheckCircle size={14} style={{ color: 'var(--success)' }} />
                ) : (
                  <XCircle size={14} style={{ color: 'var(--error)' }} />
                )}
                <span className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                  {r.path}
                </span>
              </div>
              {r.issues.length > 0 && (
                <div className="space-y-0.5">
                  {r.issues.map((issue, j) => (
                    <div key={j} className="text-xs" style={{ color: 'var(--error)' }}>{issue}</div>
                  ))}
                </div>
              )}
              {r.warnings.length > 0 && (
                <div className="space-y-0.5">
                  {r.warnings.map((w, j) => (
                    <div key={j} className="text-xs" style={{ color: 'var(--warning)' }}>{w}</div>
                  ))}
                </div>
              )}
              {r.recommendations.length > 0 && (
                <div className="space-y-0.5">
                  {r.recommendations.map((rec, j) => (
                    <div key={j} className="text-xs" style={{ color: 'var(--accent)' }}>{rec}</div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}

// ─── Extended Health Section ────────────────────────────────────────────────

function HealthConnectionBadge({ healthy }: { healthy: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold"
      style={{
        backgroundColor: healthy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
        color: healthy ? 'var(--success)' : 'var(--error)',
      }}
    >
      {healthy ? <CheckCircle size={10} /> : <XCircle size={10} />}
      {healthy ? 'Connected' : 'Disconnected'}
    </span>
  )
}

function HealthServiceCard({ name, check }: { name: string; check: ExtendedHealthCheck }) {
  const { t } = useTranslation('settings')
  return (
    <div className="rounded-md p-3 space-y-2" style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{name}</span>
        <HealthConnectionBadge healthy={check.connection.healthy} />
      </div>

      {/* Version info */}
      {(check.api_version || check.server_info) && (
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-muted)' }}>{t('integrations.health.version')}:</span>{' '}
          <span style={{ fontFamily: 'var(--font-mono)' }}>
            {check.api_version?.version || check.server_info?.version || 'N/A'}
          </span>
          {check.server_info?.product_name && (
            <span> ({check.server_info.product_name})</span>
          )}
        </div>
      )}

      {/* Library Access */}
      {check.library_access.accessible && (
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-muted)' }}>{t('integrations.health.libraryAccess')}:</span>{' '}
          {check.library_access.series_count != null && <span>{check.library_access.series_count} series </span>}
          {check.library_access.movie_count != null && <span>{check.library_access.movie_count} movies </span>}
          {check.library_access.library_count != null && <span>{check.library_access.library_count} libraries </span>}
          {check.library_access.section_count != null && <span>{check.library_access.section_count} sections </span>}
          {check.library_access.video_sources_count != null && <span>{check.library_access.video_sources_count} sources</span>}
        </div>
      )}

      {/* Webhook Status */}
      {check.webhook_status && (
        <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span style={{ color: 'var(--text-muted)' }}>{t('integrations.health.webhookStatus')}:</span>{' '}
          {check.webhook_status.configured ? (
            <span style={{ color: 'var(--success)' }}>
              {check.webhook_status.sublarr_webhooks.length} Sublarr webhook(s)
            </span>
          ) : (
            <span style={{ color: 'var(--text-muted)' }}>Not configured</span>
          )}
        </div>
      )}

      {/* Health Issues */}
      {check.health_issues.length > 0 ? (
        <div className="space-y-1">
          <span className="text-xs font-medium" style={{ color: 'var(--warning)' }}>
            {t('integrations.health.healthIssues')} ({check.health_issues.length})
          </span>
          {check.health_issues.map((issue, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs">
              <AlertTriangle size={10} className="shrink-0 mt-0.5" style={{ color: 'var(--warning)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>
                <span className="font-medium">[{issue.type}]</span> {issue.message}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-xs" style={{ color: 'var(--success)' }}>
          {t('integrations.health.noIssues')}
        </div>
      )}
    </div>
  )
}

function ExtendedHealthSection() {
  const { t } = useTranslation('settings')
  const { data: healthData, refetch, isFetching } = useExtendedHealthAll()

  const handleRun = useCallback(() => {
    void refetch()
  }, [refetch])

  return (
    <>
      <button
        onClick={handleRun}
        disabled={isFetching}
        className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white"
        style={{ backgroundColor: 'var(--accent)', opacity: isFetching ? 0.5 : 1 }}
      >
        {isFetching ? <Loader2 size={14} className="animate-spin" /> : <Heart size={14} />}
        {t('integrations.health.runDiagnostics')}
      </button>

      {healthData && (
        <div className="space-y-4">
          {/* Sonarr */}
          {healthData.sonarr.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Sonarr</h4>
              {healthData.sonarr.map((s, i) => (
                <HealthServiceCard key={i} name={s.name} check={s} />
              ))}
            </div>
          )}

          {/* Radarr */}
          {healthData.radarr.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Radarr</h4>
              {healthData.radarr.map((r, i) => (
                <HealthServiceCard key={i} name={r.name} check={r} />
              ))}
            </div>
          )}

          {/* Jellyfin */}
          {healthData.jellyfin && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Jellyfin / Emby</h4>
              <HealthServiceCard name="Jellyfin" check={healthData.jellyfin} />
            </div>
          )}

          {/* Media Servers */}
          {healthData.media_servers.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Media Servers</h4>
              {healthData.media_servers.map((ms, i) => (
                <HealthServiceCard key={i} name={`${ms.name} (${ms.type})`} check={ms} />
              ))}
            </div>
          )}
        </div>
      )}
    </>
  )
}

// ─── Export Configuration Section ───────────────────────────────────────────

function ExportConfigSection() {
  const { t } = useTranslation('settings')
  const [format, setFormat] = useState('generic')
  const [includeSecrets, setIncludeSecrets] = useState(false)
  const exportConfig = useExportIntegrationConfig()
  const exportZip = useExportIntegrationConfigZip()

  const handleExport = useCallback(() => {
    exportConfig.mutate({ format, includeSecrets }, {
      onSuccess: (data: ExportResult) => {
        const isJson = data.content_type?.includes('json')
        const content = isJson ? JSON.stringify(data.data, null, 2) : String(data.data)
        const blob = new Blob([content], { type: data.content_type })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = data.filename
        a.click()
        URL.revokeObjectURL(url)
        toast('Config exported')
        if (data.warnings.length > 0) {
          data.warnings.forEach(w => toast(w, 'error'))
        }
      },
      onError: () => toast('Export failed', 'error'),
    })
  }, [format, includeSecrets, exportConfig])

  const handleExportAll = useCallback(() => {
    const allFormats = ['bazarr', 'plex', 'kodi', 'generic']
    exportZip.mutate({ formats: allFormats, includeSecrets }, {
      onSuccess: (blob: Blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `sublarr-export-${new Date().toISOString().slice(0, 10)}.zip`
        a.click()
        URL.revokeObjectURL(url)
        toast('ZIP export downloaded')
      },
      onError: () => toast('ZIP export failed', 'error'),
    })
  }, [includeSecrets, exportZip])

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: '13px',
  }

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('integrations.export.format')}
          </label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="w-full px-3 py-2 rounded-md text-sm focus:outline-none"
            style={inputStyle}
          >
            <option value="bazarr">Bazarr Compatible</option>
            <option value="plex">Plex Manifest</option>
            <option value="kodi">Kodi</option>
            <option value="generic">Generic JSON</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            &nbsp;
          </label>
          <label className="flex items-center gap-2 px-3 py-2 cursor-pointer">
            <input
              type="checkbox"
              checked={includeSecrets}
              onChange={(e) => setIncludeSecrets(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {t('integrations.export.includeSecrets')}
            </span>
          </label>
        </div>
      </div>

      {includeSecrets && (
        <div className="flex items-start gap-2 text-xs px-3 py-2 rounded-md"
          style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: 'var(--warning)' }}
        >
          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
          <span>{t('integrations.export.secretsWarning')}</span>
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={handleExport}
          disabled={exportConfig.isPending}
          className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--accent)', opacity: exportConfig.isPending ? 0.5 : 1 }}
        >
          {exportConfig.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
          {t('integrations.export.export')}
        </button>
        <button
          onClick={handleExportAll}
          disabled={exportZip.isPending}
          className="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
            opacity: exportZip.isPending ? 0.5 : 1,
          }}
        >
          {exportZip.isPending ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
          {t('integrations.export.exportAll')}
        </button>
      </div>

      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {t('integrations.export.recommended')}
      </p>
      {format === 'bazarr' && (
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          {t('integrations.export.bazarrNote')}
        </p>
      )}
    </>
  )
}

// ─── Main IntegrationsTab ───────────────────────────────────────────────────

export function IntegrationsTab() {
  const { t } = useTranslation('settings')

  return (
    <div className="space-y-4">
      <Section
        title={t('integrations.bazarr.title')}
        icon={<FileJson size={14} />}
        defaultOpen={true}
      >
        <BazarrMigrationSection />
      </Section>

      <Section
        title={t('integrations.compat.title')}
        icon={<Shield size={14} />}
        defaultOpen={false}
      >
        <CompatCheckSection />
      </Section>

      <Section
        title={t('integrations.health.title')}
        icon={<Heart size={14} />}
        defaultOpen={false}
      >
        <ExtendedHealthSection />
      </Section>

      <Section
        title={t('integrations.export.title')}
        icon={<Download size={14} />}
        defaultOpen={false}
      >
        <ExportConfigSection />
      </Section>
    </div>
  )
}
