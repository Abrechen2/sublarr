import { useState, useRef, useEffect } from 'react'
import { useLogs } from '@/hooks/useApi'
import { useWebSocket } from '@/hooks/useWebSocket'
import { Pause, Play, Search, ArrowDown } from 'lucide-react'

const LOG_LEVELS = ['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR']

export function LogsPage() {
  const [level, setLevel] = useState<string | undefined>()
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [liveEntries, setLiveEntries] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)

  const { data: logs } = useLogs(500, level)

  useWebSocket({
    onLogEntry: (data: unknown) => {
      const entry = data as { message: string }
      if (entry?.message) {
        setLiveEntries((prev) => [...prev.slice(-500), entry.message])
      }
    },
  })

  const allEntries = [...(logs?.entries || []), ...liveEntries]
  const filtered = search
    ? allEntries.filter((e) => e.toLowerCase().includes(search.toLowerCase()))
    : allEntries

  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [filtered, autoScroll])

  const getLevelColor = (line: string) => {
    if (line.includes('[ERROR]')) return 'var(--error)'
    if (line.includes('[WARNING]')) return 'var(--warning)'
    if (line.includes('[DEBUG]')) return 'var(--text-secondary)'
    return 'var(--text-primary)'
  }

  return (
    <div className="space-y-4 h-[calc(100vh-8rem)] flex flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Logs</h1>
        <div className="flex items-center gap-3">
          {/* Level Filter */}
          <div className="flex flex-wrap gap-1">
            {LOG_LEVELS.map((l) => (
              <button
                key={l}
                onClick={() => setLevel(l === 'ALL' ? undefined : l)}
                className="px-2.5 py-1 rounded text-xs font-medium transition-all duration-200 hover:shadow-sm"
                style={{
                  backgroundColor: (l === 'ALL' && !level) || level === l
                    ? 'rgba(29, 184, 212, 0.15)'
                    : 'transparent',
                  color: (l === 'ALL' && !level) || level === l
                    ? 'var(--accent)'
                    : 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                }}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--text-secondary)' }} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search logs..."
              className="pl-8 pr-3 py-1.5 rounded-lg text-xs w-48 focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className="p-1.5 rounded-lg transition-all duration-200 hover:shadow-sm"
            style={{
              border: '1px solid var(--border)',
              color: autoScroll ? 'var(--accent)' : 'var(--text-secondary)',
              backgroundColor: 'var(--bg-surface)',
            }}
            title={autoScroll ? 'Auto-scroll ON' : 'Auto-scroll OFF'}
          >
            {autoScroll ? <ArrowDown size={16} /> : <Pause size={16} />}
          </button>
        </div>
      </div>

      {/* Log viewer */}
      <div
        ref={logRef}
        className="flex-1 rounded-xl overflow-auto font-mono text-xs leading-relaxed p-4 shadow-sm"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
        }}
      >
        {filtered.length > 0 ? (
          filtered.map((entry, i) => (
            <div
              key={i}
              className="py-0.5 hover:opacity-80"
              style={{ color: getLevelColor(entry) }}
            >
              {entry}
            </div>
          ))
        ) : (
          <div className="text-center py-8" style={{ color: 'var(--text-secondary)' }}>
            No log entries{level ? ` for level ${level}` : ''}
          </div>
        )}
      </div>
    </div>
  )
}
