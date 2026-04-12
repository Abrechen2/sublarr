import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, LayoutDashboard, SlidersHorizontal } from 'lucide-react'
import { FIELDS } from '@/pages/Settings/settingsFields'

// ─── Search data ─────────────────────────────────────────────────────────────

type SearchEntry = {
  type: 'page' | 'setting'
  label: string
  sublabel: string
  searchText: string
  href: string
  fieldKey?: string
}

const TAB_TO_ROUTE: Record<string, string> = {
  General: '/settings/general',
  Translation: '/settings/translation',
  Automation: '/settings/automation',
  Wanted: '/settings/automation',
  Sonarr: '/settings/connections',
  Radarr: '/settings/connections',
  'Library Sources': '/settings/connections',
  'Media Servers': '/settings/connections',
  'API Keys': '/settings/connections',
  Languages: '/settings/subtitles/languages',
  Scoring: '/settings/subtitles/scoring',
  'Subtitle Tools': '/settings/subtitles/format',
  Cleanup: '/settings/cleanup',
  Whisper: '/settings/providers/transcription',
}

const TAB_TO_LABEL: Record<string, string> = {
  General: 'Allgemein',
  Translation: 'Übersetzung',
  Automation: 'Automatisierung',
  Wanted: 'Automatisierung',
  Sonarr: 'Verbindungen',
  Radarr: 'Verbindungen',
  'Library Sources': 'Verbindungen',
  'Media Servers': 'Verbindungen',
  'API Keys': 'Verbindungen',
  Languages: 'Untertitel',
  Scoring: 'Untertitel',
  'Subtitle Tools': 'Untertitel',
  Cleanup: 'Untertitel',
  Whisper: 'Provider',
}

const PAGES: SearchEntry[] = [
  { type: 'page', label: 'App & Oberfläche', sublabel: 'Allgemein', searchText: 'allgemein app oberfläche', href: '/settings/general' },
  { type: 'page', label: 'Sonarr, Radarr & Medienserver', sublabel: 'Verbindungen', searchText: 'sonarr radarr medienserver verbindungen', href: '/settings/connections' },
  { type: 'page', label: 'Metadaten', sublabel: 'Verbindungen', searchText: 'metadaten tmdb tvdb verbindungen', href: '/settings/connections/metadata' },
  { type: 'page', label: 'Sprachen & Profile', sublabel: 'Untertitel', searchText: 'sprachen profile untertitel language', href: '/settings/subtitles/languages' },
  { type: 'page', label: 'Scoring', sublabel: 'Untertitel', searchText: 'scoring punkte bewertung untertitel', href: '/settings/subtitles/scoring' },
  { type: 'page', label: 'Format & Benennung', sublabel: 'Untertitel', searchText: 'format benennung srt ass datei', href: '/settings/subtitles/format' },
  { type: 'page', label: 'Bereinigung', sublabel: 'Untertitel', searchText: 'bereinigung cleanup duplikate', href: '/settings/cleanup' },
  { type: 'page', label: 'Stream-Verwaltung', sublabel: 'Untertitel', searchText: 'stream verwaltung remux mkv', href: '/settings/subtitles/stream-management' },
  { type: 'page', label: 'Provider & Zugangsdaten', sublabel: 'Provider', searchText: 'provider zugangsdaten opensubtitles', href: '/settings/providers' },
  { type: 'page', label: 'Transkription', sublabel: 'Provider', searchText: 'transkription whisper speech', href: '/settings/providers/transcription' },
  { type: 'page', label: 'Suche, Scan & Upgrades', sublabel: 'Automatisierung', searchText: 'suche scan upgrades automatisierung webhook', href: '/settings/automation' },
  { type: 'page', label: 'Post-Processing', sublabel: 'Automatisierung', searchText: 'post processing nachbearbeitung automation', href: '/settings/automation/post-processing' },
  { type: 'page', label: 'Backends & Glossar', sublabel: 'Übersetzung', searchText: 'backends glossar übersetzung ollama llm', href: '/settings/translation' },
  { type: 'page', label: 'Kanäle & Vorlagen', sublabel: 'Benachrichtigungen', searchText: 'kanäle vorlagen benachrichtigungen discord', href: '/settings/notifications' },
  { type: 'page', label: 'Sicherheit, Backup & Logs', sublabel: 'System', searchText: 'sicherheit backup logs system security', href: '/settings/system' },
  { type: 'page', label: 'Hooks & Webhooks', sublabel: 'System', searchText: 'hooks webhooks system scripts', href: '/settings/system/hooks' },
  { type: 'page', label: 'Über Sublarr', sublabel: 'Über', searchText: 'über version info about', href: '/settings/about' },
]

const FIELD_ENTRIES: SearchEntry[] = FIELDS.map((f) => ({
  type: 'setting',
  label: f.label,
  sublabel: TAB_TO_LABEL[f.tab] ?? f.tab,
  searchText: [f.label, f.description ?? '', f.tab].join(' ').toLowerCase(),
  href: TAB_TO_ROUTE[f.tab] ?? '/settings/general',
  fieldKey: f.key,
}))

const ALL_ENTRIES: SearchEntry[] = [...PAGES, ...FIELD_ENTRIES]

// ─── Component ───────────────────────────────────────────────────────────────

interface SettingsSearchModalProps {
  open: boolean
  onClose: () => void
}

export function SettingsSearchModal({ open, onClose }: SettingsSearchModalProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const results = useMemo<SearchEntry[]>(() => {
    if (!query.trim()) return PAGES.slice(0, 8)
    const q = query.toLowerCase()
    return ALL_ENTRIES.filter((e) => e.searchText.includes(q) || e.label.toLowerCase().includes(q)).slice(0, 12)
  }, [query])

  // Reset active index when results change
  useEffect(() => { setActiveIndex(0) }, [results])

  // Auto-focus + reset on open
  useEffect(() => {
    if (open) {
      setQuery('')
      setActiveIndex(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const handleSelect = (entry: SearchEntry) => {
    if (entry.type === 'setting' && entry.fieldKey) {
      console.log('[HL] storing fieldKey:', entry.fieldKey, '→', entry.href)
      sessionStorage.setItem('highlight-setting', entry.fieldKey)
      requestAnimationFrame(() => {
        console.log('[HL] dispatching settings-highlight-request event')
        window.dispatchEvent(new CustomEvent('settings-highlight-request'))
      })
    }
    navigate(entry.href)
    onClose()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (results[activeIndex]) handleSelect(results[activeIndex])
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center"
      style={{ backgroundColor: 'rgba(0,0,0,0.55)', paddingTop: '15vh' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl overflow-hidden shadow-2xl"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <Search size={15} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="Einstellung suchen…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none"
            style={{ color: 'var(--text-primary)' }}
          />
          <kbd
            className="px-1.5 py-0.5 rounded text-[10px] font-mono"
            style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}
          >
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-1">
          {results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              Keine Einstellung gefunden
            </div>
          ) : (
            results.map((entry, i) => (
              <button
                key={`${entry.href}-${entry.label}`}
                className="w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors duration-75"
                style={{
                  backgroundColor: i === activeIndex ? 'var(--accent-bg)' : 'transparent',
                }}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => handleSelect(entry)}
              >
                {entry.type === 'page' ? (
                  <LayoutDashboard
                    size={14}
                    style={{ color: i === activeIndex ? 'var(--accent)' : 'var(--text-muted)', flexShrink: 0 }}
                  />
                ) : (
                  <SlidersHorizontal
                    size={14}
                    style={{ color: i === activeIndex ? 'var(--accent)' : 'var(--text-muted)', flexShrink: 0 }}
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div
                    className="text-sm font-medium truncate"
                    style={{ color: i === activeIndex ? 'var(--accent)' : 'var(--text-primary)' }}
                  >
                    {entry.label}
                  </div>
                  <div className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                    {entry.sublabel}
                  </div>
                </div>
                {entry.type === 'page' && (
                  <span className="text-[10px] shrink-0 font-medium" style={{ color: 'var(--text-muted)' }}>
                    Seite
                  </span>
                )}
              </button>
            ))
          )}
        </div>

        {/* Footer */}
        <div
          className="flex items-center gap-4 px-4 py-2 text-[10px] font-mono"
          style={{ borderTop: '1px solid var(--border)', color: 'var(--text-muted)' }}
        >
          <span>↑↓ navigieren</span>
          <span>↵ öffnen</span>
          <span>Esc schließen</span>
        </div>
      </div>
    </div>
  )
}
