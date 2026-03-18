import { useState, useRef, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useVirtualizer, type VirtualItem } from '@tanstack/react-virtual'
import { useLogs } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Pause, Search, ArrowDown, Download } from 'lucide-react'

const ROW_HEIGHT = 30
const OVERSCAN = 10

const LOG_LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] as const
const LEVEL_SEVERITY: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 }

const CATEGORY_PREFIXES: Record<string, string[]> = {
  scanner:     ['wanted_scanner', 'standalone'],
  translation: ['translation', 'llm_utils'],
  providers:   ['jimaku', 'podnapisi', 'opensubtitles', 'subdl', 'addic7ed'],
  jobs:        ['apscheduler', 'worker'],
  auth:        ['auth', 'auth_ui'],
  api_access:  ['werkzeug'],
}

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
  const parentRef = useRef<HTMLDivElement>(null)

  const { data: logs } = useLogs(500)

  useWebSocket({
    onLogEntry: (data: unknown) => {
      const entry = data as { message: string }
      if (entry?.message) {
        setLiveEntries((prev) => [...prev.slice(-500), entry.message])
      }
    },
  })

  // Fix 6: deduplicate API-polled entries against live WebSocket entries by content
  const allEntries = useMemo(() => {
    const wsSet = new Set(liveEntries)
    const apiEntries = (logs?.entries || []).filter((e) => !wsSet.has(e))
    return [...apiEntries, ...liveEntries]
  }, [logs?.entries, liveEntries])
  const minSeverity = level ? LEVEL_SEVERITY[level] ?? 0 : -1
  const filtered = allEntries.filter((e) => {
    if (level && LEVEL_SEVERITY[getLineLevel(e)] < minSeverity) return false
    if (search && !e.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const logViewPrefs = useMemo(() => {
    try {
      const raw = localStorage.getItem('sublarr_log_view_prefs')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }, [])

  function isLineVisible(line: string): boolean {
    if (!logViewPrefs?.categories) return true
    for (const [cat, prefixes] of Object.entries(CATEGORY_PREFIXES)) {
      if (logViewPrefs.categories[cat] === false) {
        if ((prefixes as string[]).some(prefix => line.includes(` ${prefix}:`))) return false
      }
    }
    return true
  }

  function formatLine(line: string): string {
    if (logViewPrefs?.showTimestamps === false) {
      return line.replace(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+ /, '')
    }
    return line
  }

  const visibleLogs = useMemo(
    () => filtered.filter(isLineVisible),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filtered],
  )

  const virtualizer = useVirtualizer({
    count: visibleLogs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  })

  const virtualItems = virtualizer.getVirtualItems()
  const totalHeight = virtualizer.getTotalSize()

  useEffect(() => {
    if (autoScroll && parentRef.current) {
      parentRef.current.scrollTop = parentRef.current.scrollHeight
    }
  }, [visibleLogs.length, autoScroll])

  const getLevelColor = (line: string) => {
    if (line.includes('[ERROR]')) return 'var(--error)'
    if (line.includes('[WARNING]')) return 'var(--warning)'
    if (line.includes('[DEBUG]')) return 'var(--text-muted)'
    return 'var(--text-primary)'
  }

  const handleDownload = () => {
    window.open('/api/v1/logs/download', '_blank')
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

      {/* Log viewer -- terminal style, virtualized */}
      <div
        ref={parentRef}
        className="flex-1 rounded-lg overflow-auto p-4"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          lineHeight: '1.6',
        }}
      >
        {visibleLogs.length > 0 ? (
          <div
            style={{
              height: `${totalHeight}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualItems.map((virtualRow: VirtualItem) => {
              const entry = visibleLogs[virtualRow.index]
              return (
                <div
                  key={virtualRow.key}
                  data-index={virtualRow.index}
                  className="transition-opacity duration-100 hover:opacity-80 absolute left-0 w-full flex items-center"
                  style={{
                    color: getLevelColor(entry),
                    transform: `translateY(${virtualRow.start}px)`,
                    height: `${ROW_HEIGHT}px`,
                    whiteSpace: logViewPrefs?.wrapLines ? 'pre-wrap' : 'pre',
                  }}
                >
                  {formatLine(entry)}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="text-center py-8" style={{ color: 'var(--text-secondary)' }}>
            {level ? t('no_logs_for_level', { level }) : t('no_logs')}
          </div>
        )}
      </div>
    </div>
  )
}
