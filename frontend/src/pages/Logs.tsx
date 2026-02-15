import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLogs } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Pause, Play, Search, ArrowDown } from 'lucide-react'

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
  const logRef = useRef<HTMLDivElement>(null)

  const { data: logs } = useLogs(500)

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

      {/* Log viewer — terminal style */}
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
    </div>
  )
}
