import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Search, Pencil, MoreHorizontal, Eye, Columns2, Timer,
  RefreshCw, Clapperboard, ShieldCheck, Database, ScanSearch, Clock, Loader2, ChevronUp,
} from 'lucide-react'
import type { EpisodeInfo } from '@/lib/types'

interface EpisodeActionMenuProps {
  ep: EpisodeInfo
  isExpanded: boolean
  mode: string | undefined
  searchLoading: boolean
  historyLoading: boolean
  /** Path of first available subtitle (ass/srt), or null */
  firstSubPath: string | null
  /** True if at least 2 subtitle files exist */
  hasMultipleSubs: boolean
  onSearch: () => void
  onEditSub: (filePath: string) => void
  onPreviewSub: (filePath: string) => void
  onCompare: () => void
  onSync: (filePath: string) => void
  onAutoSync: (subtitlePath: string, videoPath: string) => void
  onVideoSync: (subtitlePath: string) => void
  onHealthCheck: (filePath: string) => void
  onTracks: () => void
  onInteractiveSearch: () => void
  onHistory: () => void
  onClose: () => void
}

function deriveFirstEditPath(ep: EpisodeInfo): string | null {
  const entry = Object.entries(ep.subtitles).find(([, f]) => f === 'ass' || f === 'srt')
  if (!entry) return null
  const [lang, format] = entry
  const lastDot = ep.file_path.lastIndexOf('.')
  const base = lastDot > 0 ? ep.file_path.substring(0, lastDot) : ep.file_path
  return `${base}.${lang}.${format}`
}

export function EpisodeActionMenu({
  ep,
  isExpanded,
  mode,
  searchLoading,
  historyLoading,
  firstSubPath,
  hasMultipleSubs,
  onSearch,
  onEditSub,
  onPreviewSub,
  onCompare,
  onSync,
  onAutoSync,
  onVideoSync,
  onHealthCheck,
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

  const hasAnySub = ep.has_file && firstSubPath !== null
  const editPath = hasAnySub ? deriveFirstEditPath(ep) : null

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

      {/* Primary: Edit (only when subtitle exists) */}
      {editPath && (
        <button
          onClick={() => onEditSub(editPath)}
          className={`${iconBtn} flex items-center gap-1 px-2 text-xs font-medium`}
          style={{ color: muted }}
          title={t('episode_actions.edit_subtitle')}
          onMouseEnter={(e) => { e.currentTarget.style.color = accent; e.currentTarget.style.backgroundColor = accentBg }}
          onMouseLeave={(e) => { e.currentTarget.style.color = muted; e.currentTarget.style.backgroundColor = '' }}
        >
          <Pencil size={13} />
          <span>{t('episode_actions.edit_subtitle')}</span>
        </button>
      )}

      {/* More dropdown */}
      <div className="relative" ref={dropdownRef}>
        <button
          data-testid="episode-actions-menu"
          onClick={() => setDropdownOpen((v) => !v)}
          className={iconBtn}
          style={{ color: dropdownOpen ? accent : muted, backgroundColor: dropdownOpen ? accentBg : '' }}
          title="More actions"
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
            {/* Preview */}
            {firstSubPath && (
              <DropdownItem
                icon={<Eye size={13} />}
                label={t('episode_actions.preview_subtitle')}
                onClick={() => { onPreviewSub(firstSubPath); setDropdownOpen(false) }}
              />
            )}

            {/* Compare */}
            {hasMultipleSubs && (
              <DropdownItem
                icon={<Columns2 size={13} />}
                label={t('episode_actions.compare_subtitles')}
                onClick={() => { onCompare(); setDropdownOpen(false) }}
              />
            )}

            {/* Divider: Timing group */}
            {hasAnySub && firstSubPath && (
              <>
                <DropdownDivider label="Timing" />
                <DropdownItem
                  icon={<Timer size={13} />}
                  label={t('episode_actions.sync_timing')}
                  onClick={() => { onSync(firstSubPath); setDropdownOpen(false) }}
                />
                <DropdownItem
                  icon={<RefreshCw size={13} />}
                  label={t('episode_actions.auto_sync')}
                  onClick={() => { onAutoSync(firstSubPath, ep.file_path); setDropdownOpen(false) }}
                />
                <DropdownItem
                  icon={<Clapperboard size={13} />}
                  label={t('episode_actions.video_sync')}
                  onClick={() => { onVideoSync(firstSubPath); setDropdownOpen(false) }}
                />
              </>
            )}

            {/* Divider: Analysis group */}
            {ep.has_file && (
              <>
                <DropdownDivider label="Analyse" />
                {hasAnySub && firstSubPath && (
                  <DropdownItem
                    icon={<ShieldCheck size={13} />}
                    label={t('episode_actions.health_check')}
                    onClick={() => { onHealthCheck(firstSubPath); setDropdownOpen(false) }}
                  />
                )}
                <DropdownItem
                  icon={<Database size={13} />}
                  label={t('episode_actions.embedded_tracks')}
                  onClick={() => { onTracks(); setDropdownOpen(false) }}
                />
              </>
            )}

            {/* Interactive Search */}
            {ep.has_file && (
              <>
                <DropdownDivider />
                <DropdownItem
                  icon={<ScanSearch size={13} />}
                  label={t('episode_actions.interactive_search')}
                  onClick={() => { onInteractiveSearch(); setDropdownOpen(false) }}
                />
              </>
            )}

            {/* History */}
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

function DropdownDivider({ label }: { label?: string }) {
  return (
    <div
      className="mx-3 my-1 flex items-center gap-2"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      {label && (
        <span
          className="text-[10px] uppercase tracking-wider pt-1"
          style={{ color: 'var(--text-muted)' }}
        >
          {label}
        </span>
      )}
    </div>
  )
}
