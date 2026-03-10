import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Download, ChevronDown } from 'lucide-react'
import { useStatistics, useExportStatistics } from '@/hooks/useApi'
import { TranslationChart } from '@/components/charts/TranslationChart'
import { ProviderChart } from '@/components/charts/ProviderChart'
import { FormatChart } from '@/components/charts/FormatChart'
import { DownloadChart } from '@/components/charts/DownloadChart'
import { QualityTrendChart } from '@/components/charts/QualityTrendChart'
import { toast } from '@/components/shared/Toast'
import type { SeriesQuality } from '@/lib/types'

const RANGES = ['7d', '30d', '90d', '365d'] as const

function ScoreBar({ pct }: { pct: number }) {
  const color = pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--error)'
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 rounded-full overflow-hidden"
        style={{ backgroundColor: 'var(--bg-primary)', height: 6 }}
      >
        <div style={{ width: `${pct}%`, backgroundColor: color, height: '100%', borderRadius: 'inherit' }} />
      </div>
      <span className="text-xs tabular-nums w-8 text-right" style={{ color: 'var(--text-muted)' }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

function SeriesQualityTable({ data }: { data: SeriesQuality[] }) {
  const [sortBy, setSortBy] = useState<'avg_score' | 'download_count'>('download_count')
  const sorted = [...data].sort((a, b) => b[sortBy] - a[sortBy])
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-muted)' }}>
            <th className="text-left py-2 pr-3 font-medium">Series</th>
            <th className="text-left py-2 px-3 font-medium">Formats</th>
            <th
              className="text-left py-2 px-3 font-medium cursor-pointer select-none"
              onClick={() => setSortBy('avg_score')}
              style={{ color: sortBy === 'avg_score' ? 'var(--accent)' : undefined }}
            >
              Quality {sortBy === 'avg_score' ? '▼' : ''}
            </th>
            <th
              className="text-left py-2 px-3 font-medium cursor-pointer select-none"
              onClick={() => setSortBy('download_count')}
              style={{ color: sortBy === 'download_count' ? 'var(--accent)' : undefined }}
            >
              Downloads {sortBy === 'download_count' ? '▼' : ''}
            </th>
            <th className="text-left py-2 pl-3 font-medium">Last Download</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <tr
              key={s.title}
              style={{ borderBottom: '1px solid var(--border)' }}
            >
              <td className="py-2 pr-3 font-medium" style={{ color: 'var(--text-primary)', maxWidth: 200 }}>
                <span className="truncate block">{s.title}</span>
              </td>
              <td className="py-2 px-3" style={{ color: 'var(--text-muted)' }}>
                {s.formats.filter(Boolean).join(', ').toUpperCase() || '—'}
              </td>
              <td className="py-2 px-3" style={{ minWidth: 140 }}>
                <ScoreBar pct={s.avg_score_pct} />
              </td>
              <td className="py-2 px-3 tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                {s.download_count}
              </td>
              <td className="py-2 pl-3" style={{ color: 'var(--text-muted)' }}>
                {s.last_download ? s.last_download.slice(0, 10) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatisticsPage() {
  const { t } = useTranslation('statistics')
  const [range, setRange] = useState<string>('30d')
  const [exportOpen, setExportOpen] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)
  const { data, isLoading } = useStatistics(range)
  const exportMutation = useExportStatistics()

  const handleExport = (format: 'json' | 'csv') => {
    setExportOpen(false)
    exportMutation.mutate({ range, format }, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `sublarr-statistics-${range}.${format}`
        a.click()
        URL.revokeObjectURL(url)
        toast(t('exported', { format: format.toUpperCase() }))
      },
      onError: () => toast(t('export_failed'), 'error'),
    })
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1>{t('title')}</h1>
        <div className="flex items-center gap-2">
          {/* Range filter */}
          <div className="flex gap-1">
            {RANGES.map((r) => {
              const isActive = range === r
              return (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className="px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                  }}
                >
                  {r}
                </button>
              )
            })}
          </div>

          {/* Export dropdown */}
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen(!exportOpen)}
              disabled={exportMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-surface)',
              }}
            >
              {exportMutation.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Download size={12} />
              )}
              {t('export')}
              <ChevronDown size={10} />
            </button>
            {exportOpen && (
              <div
                className="absolute right-0 mt-1 rounded-md shadow-lg z-10 overflow-hidden"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  minWidth: '120px',
                }}
              >
                <button
                  onClick={() => handleExport('json')}
                  className="block w-full text-left px-3 py-2 text-xs transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                >
                  {t('export_json')}
                </button>
                <button
                  onClick={() => handleExport('csv')}
                  className="block w-full text-left px-3 py-2 text-xs transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                >
                  {t('export_csv')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Charts */}
      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className={`rounded-lg p-5 ${i === 1 || i === 4 ? 'lg:col-span-2' : ''}`}
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              <div className="h-6 w-40 rounded mb-4" style={{ backgroundColor: 'var(--bg-primary)' }} />
              <div className="flex items-center justify-center" style={{ height: i === 1 ? 300 : 250 }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--text-muted)' }} />
              </div>
            </div>
          ))}
        </div>
      ) : !data || data.daily.length === 0 ? (
        <div
          className="rounded-lg p-12 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('no_data')}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Row 1: Translation chart (full width) */}
          <div
            className="lg:col-span-2 rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              {t('charts.translations')}
            </h3>
            <TranslationChart data={data.daily} />
          </div>

          {/* Row 2: Provider chart (left) + Format chart (right) */}
          <div
            className="rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              {t('charts.providers')}
            </h3>
            <ProviderChart data={data.providers} />
          </div>

          <div
            className="rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              {t('charts.format')}
            </h3>
            <FormatChart data={data.by_format} />
          </div>

          {/* Row 3: Download chart (full width) */}
          <div
            className="lg:col-span-2 rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
              {t('charts.downloads_by_provider')}
            </h3>
            <DownloadChart data={data.downloads_by_provider} />
          </div>

          {/* Row 4: Quality trend (full width) */}
          {data.quality_trend && data.quality_trend.length > 0 && (
            <div
              className="lg:col-span-2 rounded-lg p-5"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                {t('charts.quality_trend', 'Subtitle Quality Trend')}
              </h3>
              <QualityTrendChart data={data.quality_trend} />
            </div>
          )}

          {/* Row 5: Per-series quality (full width) */}
          {data.series_quality && data.series_quality.length > 0 && (
            <div
              className="lg:col-span-2 rounded-lg p-5"
              style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
            >
              <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
                {t('charts.series_quality', 'Series Subtitle Quality')}
              </h3>
              <SeriesQualityTable data={data.series_quality} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
