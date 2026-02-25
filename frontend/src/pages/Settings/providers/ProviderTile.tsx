import { Pencil, Download, Database, Clock } from 'lucide-react'
import type { ProviderInfo } from '@/lib/types'
import { getStatusColor, getStatusLabel, getStatusBg, getSuccessRateColor } from './providerUtils'

interface ProviderTileProps {
  provider: ProviderInfo
  cacheCount: number
  priority: number
  testResult?: { healthy: boolean; message: string } | 'testing'
  onOpenEdit: () => void
}

export function ProviderTile({ provider, cacheCount, priority, onOpenEdit }: ProviderTileProps) {
  const statusColor = getStatusColor(provider)
  const statusLabel = getStatusLabel(provider)
  const statusBg = getStatusBg(provider)
  const hasStats = provider.stats && provider.stats.total_searches > 0

  return (
    <button
      onClick={onOpenEdit}
      className="relative text-left rounded p-3 transition-all duration-150 group"
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        opacity: provider.enabled ? 1 : 0.65,
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--accent-dim)'
        e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.backgroundColor = 'var(--bg-surface)'
      }}
    >
      {/* Edit icon — top right */}
      <Pencil
        size={12}
        className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity"
        style={{ color: 'var(--accent)' }}
      />

      {/* Provider name + rank */}
      <div className="flex items-center justify-between pr-4 mb-1.5">
        <span
          className="text-[13px] font-semibold capitalize truncate"
          style={{ color: 'var(--text-primary)' }}
        >
          {provider.name.replace(/_/g, ' ')}
        </span>
        <span className="text-[10px] shrink-0 ml-1" style={{ color: 'var(--text-muted)' }}>
          #{priority}
        </span>
      </div>

      {/* Status badge */}
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium mb-2"
        style={{ backgroundColor: statusBg, color: statusColor }}
      >
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: statusColor }} />
        {statusLabel}
      </span>

      {/* Stats row */}
      {provider.enabled && (
        <div className="flex items-center gap-2.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
          <span className="flex items-center gap-1">
            <Download size={10} />
            {provider.downloads}
          </span>
          <span className="flex items-center gap-1">
            <Database size={10} />
            {cacheCount}
          </span>
          {hasStats && provider.stats.avg_response_time_ms > 0 && (
            <span className="flex items-center gap-1">
              <Clock size={10} />
              {Math.round(provider.stats.avg_response_time_ms)}ms
            </span>
          )}
        </div>
      )}

      {/* Success rate bar */}
      {provider.enabled && hasStats && (
        <div className="mt-2 h-0.5 rounded-full" style={{ backgroundColor: 'var(--bg-primary)' }}>
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${provider.stats.success_rate * 100}%`,
              backgroundColor: getSuccessRateColor(provider.stats.success_rate),
            }}
          />
        </div>
      )}
    </button>
  )
}
