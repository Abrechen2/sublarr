import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Search, MoreHorizontal, Columns2, Database, ScanSearch, Clock, Loader2, ChevronUp,
} from 'lucide-react'
import type { EpisodeInfo } from '@/lib/types'

interface EpisodeActionMenuProps {
  ep: EpisodeInfo
  isExpanded: boolean
  mode: string | undefined
  searchLoading: boolean
  historyLoading: boolean
  /** True if at least 2 subtitle files exist (gates the Compare entry) */
  hasMultipleSubs: boolean
  onSearch: () => void
  onCompare: () => void
  onTracks: () => void
  onInteractiveSearch: () => void
  onHistory: () => void
  onClose: () => void
}

export function EpisodeActionMenu({
  ep,
  isExpanded,
  mode,
  searchLoading,
  historyLoading,
  hasMultipleSubs,
  onSearch,
  onCompare,
  onTracks,
  onInteractiveSearch,
  onHistory,
  onClose,
}: EpisodeActionMenuProps) {
  const { t } = useTranslation('library')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!dropdownOpen) return
    const handle = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [dropdownOpen])

  const iconBtn = 'p-1 rounded transition-colors'
  const muted = 'var(--text-muted)'
  const accent = 'var(--accent)'
  const accentBg = 'var(--accent-subtle)'

  return (
    <div className="flex items-center gap-0.5">
      {isExpanded && (
        <button
          onClick={onClose}
          className={iconBtn}
          style={{ color: muted }}
          title={t('series_detail.close')}
          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = muted }}
        >
          <ChevronUp size={14} />
        </button>
      )}

      {/* Primary: Search */}
      <button
        onClick={onSearch}
        disabled={!ep.has_file}
        className={`${iconBtn} flex items-center gap-1 px-2 text-xs font-medium`}
        style={{
          color: isExpanded && mode === 'search' ? accent : muted,
          opacity: ep.has_file ? 1 : 0.4,
          backgroundColor: isExpanded && mode === 'search' ? accentBg : '',
        }}
        title={t('series_detail.search_subtitles')}
        onMouseEnter={(e) => { if (ep.has_file) { e.currentTarget.style.color = accent; e.currentTarget.style.backgroundColor = accentBg } }}
        onMouseLeave={(e) => { e.currentTarget.style.color = isExpanded && mode === 'search' ? accent : muted; e.currentTarget.style.backgroundColor = isExpanded && mode === 'search' ? accentBg : '' }}
      >
        {searchLoading && isExpanded && mode === 'search' ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <Search size={13} />
        )}
        <span>{t('series_detail.search_subtitles')}</span>
      </button>

      {/* More dropdown — episode-scope only (per-sidecar actions live on the language pill) */}
      <div className="relative" ref={dropdownRef}>
        <button
          data-testid="episode-actions-menu"
          onClick={() => setDropdownOpen((v) => !v)}
          className={iconBtn}
          style={{ color: dropdownOpen ? accent : muted, backgroundColor: dropdownOpen ? accentBg : '' }}
          title={t('episode_action_menu.more_actions')}
          onMouseEnter={(e) => { e.currentTarget.style.color = accent; e.currentTarget.style.backgroundColor = accentBg }}
          onMouseLeave={(e) => { e.currentTarget.style.color = dropdownOpen ? accent : muted; e.currentTarget.style.backgroundColor = dropdownOpen ? accentBg : '' }}
        >
          <MoreHorizontal size={14} />
        </button>

        {dropdownOpen && (
          <div
            className="absolute right-0 top-7 z-50 rounded-lg shadow-lg py-1 min-w-44"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            {/* Compare — needs 2+ sidecars */}
            {hasMultipleSubs && (
              <DropdownItem
                icon={<Columns2 size={13} />}
                label={t('episode_actions.compare_subtitles')}
                onClick={() => { onCompare(); setDropdownOpen(false) }}
              />
            )}

            {/* Embedded Tracks — container-level inspection */}
            {ep.has_file && (
              <DropdownItem
                icon={<Database size={13} />}
                label={t('episode_actions.embedded_tracks')}
                onClick={() => { onTracks(); setDropdownOpen(false) }}
              />
            )}

            {/* Interactive Search — episode-level provider lookup */}
            {ep.has_file && (
              <DropdownItem
                icon={<ScanSearch size={13} />}
                label={t('episode_actions.interactive_search')}
                onClick={() => { onInteractiveSearch(); setDropdownOpen(false) }}
              />
            )}

            {/* History — episode-level history */}
            {ep.has_file && (
              <DropdownItem
                icon={historyLoading && isExpanded && mode === 'history' ? <Loader2 size={13} className="animate-spin" /> : <Clock size={13} />}
                label={t('episode_actions.history')}
                onClick={() => { onHistory(); setDropdownOpen(false) }}
                active={isExpanded && mode === 'history'}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function DropdownItem({
  icon,
  label,
  onClick,
  active = false,
}: {
  icon: React.ReactNode
  label: string
  onClick: () => void
  active?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left transition-colors"
      style={{ color: active ? 'var(--accent)' : 'var(--text-secondary)' }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)'; e.currentTarget.style.color = 'var(--text-primary)' }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = ''; e.currentTarget.style.color = active ? 'var(--accent)' : 'var(--text-secondary)' }}
    >
      {icon}
      {label}
    </button>
  )
}
