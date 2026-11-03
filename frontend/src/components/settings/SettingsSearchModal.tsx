import { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
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

/** Language-independent page definitions. Labels are translated at render time
 * (via `settings_search.pages.<id>` / `settings_search.groups.<group>`); `keywords`
 * carries German and English search terms so both languages find the page. */
interface PageDef {
  id: string
  group: string
  keywords: string
  href: string
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
  Scoring: '/settings/subtitles/scoring',
  'Subtitle Tools': '/settings/subtitles/format',
  Cleanup: '/settings/cleanup',
  Whisper: '/settings/providers/transcription',
}

/** Settings tab -> sublabel group id (translated via `settings_search.groups.*`). */
const TAB_TO_GROUP: Record<string, string> = {
  General: 'general',
  Translation: 'translation',
  Automation: 'automation',
  Wanted: 'automation',
  Sonarr: 'connections',
  Radarr: 'connections',
  'Library Sources': 'connections',
  'Media Servers': 'connections',
  'API Keys': 'connections',
  Scoring: 'subtitles',
  'Subtitle Tools': 'subtitles',
  Cleanup: 'subtitles',
  Whisper: 'providers',
}

const PAGE_DEFS: PageDef[] = [
  { id: 'general', group: 'general', keywords: 'allgemein app oberfläche general interface language theme sprache', href: '/settings/general' },
  { id: 'connections', group: 'connections', keywords: 'sonarr radarr medienserver verbindungen connections media servers jellyfin plex emby', href: '/settings/connections' },
  { id: 'metadata', group: 'connections', keywords: 'metadaten metadata tmdb tvdb verbindungen connections', href: '/settings/connections/metadata' },
  { id: 'scoring', group: 'subtitles', keywords: 'scoring punkte bewertung untertitel subtitles score points', href: '/settings/subtitles/scoring' },
  { id: 'format', group: 'subtitles', keywords: 'format benennung naming srt ass datei file', href: '/settings/subtitles/format' },
  { id: 'cleanup', group: 'subtitles', keywords: 'bereinigung cleanup duplikate duplicates', href: '/settings/cleanup' },
  { id: 'stream_management', group: 'subtitles', keywords: 'stream verwaltung management remux mkv', href: '/settings/subtitles/stream-management' },
  { id: 'providers', group: 'providers', keywords: 'provider zugangsdaten credentials login opensubtitles', href: '/settings/providers' },
  { id: 'transcription', group: 'providers', keywords: 'transkription transcription whisper speech', href: '/settings/providers/transcription' },
  { id: 'automation', group: 'automation', keywords: 'suche search scan upgrades automatisierung automation webhook', href: '/settings/automation' },
  { id: 'post_processing', group: 'automation', keywords: 'post processing nachbearbeitung automation', href: '/settings/automation/post-processing' },
  { id: 'translation', group: 'translation', keywords: 'backends glossar glossary übersetzung translation ollama llm', href: '/settings/translation' },
  { id: 'notifications', group: 'notifications', keywords: 'kanäle channels vorlagen templates benachrichtigungen notifications discord', href: '/settings/notifications' },
  { id: 'system', group: 'system', keywords: 'sicherheit security backup logs system', href: '/settings/system' },
  { id: 'hooks', group: 'system', keywords: 'hooks webhooks system scripts', href: '/settings/system/hooks' },
  { id: 'about', group: 'about', keywords: 'über about version info', href: '/settings/about' },
]

type TFn = (key: string, opts?: Record<string, unknown>) => string

/** Builds the translated search index. Called inside the component so the
 * entries follow the active UI language. */
function buildEntries(t: TFn): { pages: SearchEntry[]; all: SearchEntry[] } {
  const pages: SearchEntry[] = PAGE_DEFS.map((p) => {
    const label = t(`settings_search.pages.${p.id}`)
    const sublabel = t(`settings_search.groups.${p.group}`)
    return {
      type: 'page',
      label,
      sublabel,
      searchText: `${label} ${sublabel} ${p.keywords}`.toLowerCase(),
      href: p.href,
    }
  })
  const fields: SearchEntry[] = FIELDS.map((f) => {
    const group = TAB_TO_GROUP[f.tab]
    // Help text is searchable in both languages regardless of the UI language.
    const help = f.descriptionKey
      ? `${t(`settings:${f.descriptionKey}`, { lng: 'de' })} ${t(`settings:${f.descriptionKey}`, { lng: 'en' })}`
      : ''
    return {
      type: 'setting',
      label: f.label,
      sublabel: group ? t(`settings_search.groups.${group}`) : f.tab,
      searchText: [f.label, help, f.tab].join(' ').toLowerCase(),
      href: TAB_TO_ROUTE[f.tab] ?? '/settings/general',
      fieldKey: f.key,
    }
  })
  return { pages, all: [...pages, ...fields] }
}

// ─── Component ───────────────────────────────────────────────────────────────

interface SettingsSearchModalProps {
  open: boolean
  onClose: () => void
}

export function SettingsSearchModal({ open, onClose }: SettingsSearchModalProps) {
  const { t: tc } = useTranslation('common')
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const entries = useMemo(() => buildEntries(tc), [tc])

  const results = useMemo<SearchEntry[]>(() => {
    if (!query.trim()) return entries.pages.slice(0, 8)
    const q = query.toLowerCase()
    return entries.all.filter((e) => e.searchText.includes(q) || e.label.toLowerCase().includes(q)).slice(0, 12)
  }, [query, entries])

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
      sessionStorage.setItem('highlight-setting', entry.fieldKey)
      requestAnimationFrame(() => {
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
            placeholder={tc('ui.search_settings_placeholder')}
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
              {tc('settings_search.none_found')}
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
                    {tc('settings_search.page_badge')}
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
          <span>{tc('settings_search.hint_navigate')}</span>
          <span>{tc('settings_search.hint_open')}</span>
          <span>{tc('ui.esc_close')}</span>
        </div>
      </div>
    </div>
  )
}
