import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Download, ChevronDown } from 'lucide-react'
import { useStatistics, useExportStatistics } from '@/hooks/useApi'
import { TranslationChart } from '@/components/charts/TranslationChart'
import { ProviderChart } from '@/components/charts/ProviderChart'
import { FormatChart } from '@/components/charts/FormatChart'
import { DownloadChart } from '@/components/charts/DownloadChart'
import { toast } from '@/components/shared/Toast'

const RANGES = ['7d', '30d', '90d', '365d'] as const

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
        </div>
      )}
    </div>
  )
}
