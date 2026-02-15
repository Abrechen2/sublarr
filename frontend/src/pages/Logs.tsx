import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLogs, useLogRotation, useUpdateLogRotation } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Pause, Search, ArrowDown, Download, ChevronDown, ChevronUp, Save, Loader2 } from 'lucide-react'
import { toast } from '@/components/shared/Toast'

const LOG_LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
const LEVEL_SEVERITY: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 }

function getLineLevel(line: string): string {
  if (line.includes('[ERROR]')) return 'ERROR'
  if (line.includes('[WARNING]')) return 'WARNING'
  if (line.includes('[INFO]')) return 'INFO'
  if (line.includes('[DEBUG]')) return 'DEBUG'
  return 'INFO'
}

export function LogsPage() {
  const { t } = useTranslation('logs')
  const [level, setLevel] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [liveEntries, setLiveEntries] = useState<string[]>([])
  const [rotationOpen, setRotationOpen] = useState(false)
  const [rotationMaxSize, setRotationMaxSize] = useState(10)
  const [rotationBackupCount, setRotationBackupCount] = useState(5)
  const logRef = useRef<HTMLDivElement>(null)

  const { data: logs } = useLogs(500)
  const { data: rotationConfig } = useLogRotation()
  const updateRotation = useUpdateLogRotation()

  // Sync rotation config from API
  useEffect(() => {
    if (rotationConfig) {
      setRotationMaxSize(rotationConfig.max_size_mb)
      setRotationBackupCount(rotationConfig.backup_count)
    }
  }, [rotationConfig])

  useWebSocket({
    onLogEntry: (data: unknown) => {
      const entry = data as { message: string }
      if (entry?.message) {
        setLiveEntries((prev) => [...prev.slice(-500), entry.message])
      }
    },
  })

  const allEntries = [...(logs?.entries || []), ...liveEntries]
  const minSeverity = level ? LEVEL_SEVERITY[level] ?? 0 : -1
  const filtered = allEntries.filter((e) => {
    if (level && LEVEL_SEVERITY[getLineLevel(e)] < minSeverity) return false
    if (search && !e.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [filtered, autoScroll])

  const getLevelColor = (line: string) => {
    if (line.includes('[ERROR]')) return 'var(--error)'
    if (line.includes('[WARNING]')) return 'var(--warning)'
    if (line.includes('[DEBUG]')) return 'var(--text-muted)'
    return 'var(--text-primary)'
  }

  const handleDownload = () => {
    window.open('/api/v1/logs/download', '_blank')
  }

  const handleSaveRotation = () => {
    updateRotation.mutate(
      { max_size_mb: rotationMaxSize, backup_count: rotationBackupCount },
      {
        onSuccess: () => toast('Rotation config saved'),
        onError: () => toast('Failed to save rotation config', 'error'),
      }
    )
  }

  return (
    <div className="space-y-4 h-[calc(100vh-7rem)] flex flex-col">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1>{t('title')}</h1>
        <div className="flex items-center gap-2">
          {/* Level Filter */}
          <div className="flex gap-1">
            {LOG_LEVELS.map((l) => {
              const isActive = (l === 'ALL' && !level) || level === l
              return (
                <button
                  key={l}
                  onClick={() => setLevel(l === 'ALL' ? undefined : l)}
                  className="px-2 py-1 rounded-md text-[11px] font-medium transition-all duration-150"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'var(--bg-surface)',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--accent-dim)' : 'var(--border)'}`,
                  }}
                >
                  {l}
                </button>
              )
            })}
          </div>

          {/* Search */}
          <div className="relative">
            <Search
              size={12}
              className="absolute left-2.5 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-muted)' }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('search_placeholder')}
              className="pl-7 pr-3 py-1.5 rounded-md text-xs w-40 focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          {/* Download */}
          <button
            onClick={handleDownload}
            className="p-1.5 rounded-md transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-surface)',
            }}
            title="Download log file"
          >
            <Download size={14} />
          </button>

          {/* Auto-scroll */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className="p-1.5 rounded-md transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: autoScroll ? 'var(--accent)' : 'var(--text-muted)',
              backgroundColor: autoScroll ? 'var(--accent-subtle)' : 'var(--bg-surface)',
            }}
            title={autoScroll ? t('auto_scroll_on') : t('auto_scroll_off')}
          >
            {autoScroll ? <ArrowDown size={14} /> : <Pause size={14} />}
          </button>
        </div>
      </div>

      {/* Log viewer -- terminal style */}
      <div
        ref={logRef}
        className="flex-1 rounded-lg overflow-auto p-4"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          lineHeight: '1.6',
        }}
      >
        {filtered.length > 0 ? (
          filtered.map((entry, i) => (
            <div
              key={i}
              className="py-0.5 transition-opacity duration-100 hover:opacity-80"
              style={{ color: getLevelColor(entry) }}
            >
              {entry}
            </div>
          ))
        ) : (
          <div className="text-center py-8" style={{ color: 'var(--text-secondary)' }}>
            {level ? t('no_logs_for_level', { level }) : t('no_logs')}
          </div>
        )}
      </div>

      {/* Rotation Config (collapsible) */}
      <div
        className="rounded-lg shrink-0"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <button
          onClick={() => setRotationOpen(!rotationOpen)}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          <span>Rotation Config</span>
          {rotationOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
        {rotationOpen && (
          <div className="px-4 pb-4 pt-0 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div className="space-y-1">
                <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Max Size (MB)
                </label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={rotationMaxSize}
                  onChange={(e) => setRotationMaxSize(Math.max(1, Math.min(100, parseInt(e.target.value) || 1)))}
                  className="w-full px-3 py-2 rounded-md text-sm"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '13px',
                  }}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  Backup Count
                </label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={rotationBackupCount}
                  onChange={(e) => setRotationBackupCount(Math.max(1, Math.min(20, parseInt(e.target.value) || 1)))}
                  className="w-full px-3 py-2 rounded-md text-sm"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '13px',
                  }}
                />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                Changes take effect on next restart.
              </p>
              <button
                onClick={handleSaveRotation}
                disabled={updateRotation.isPending}
                className="flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {updateRotation.isPending ? (
                  <Loader2 size={12} className="animate-spin" />
                ) : (
                  <Save size={12} />
                )}
                Save
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
