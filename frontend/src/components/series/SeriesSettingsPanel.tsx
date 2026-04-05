import type React from 'react'
import type { SeriesDetail } from '@/lib/types'
import { Tooltip } from '@/components/shared/Tooltip'

interface SeriesSettingsPanelProps {
  readonly series: SeriesDetail
  readonly seriesId: number
  readonly showGlossary: boolean
  readonly hasFansubOverride: boolean
  readonly isExtracting: boolean
  readonly extractProgress: { current: number; total: number; filename: string } | null
  readonly onToggleGlossary: () => void
  readonly onToggleAbsoluteOrder: (enabled: boolean) => void
  readonly onRefreshAnidb: () => void
  readonly onExtract: () => void
  readonly onCleanup: () => void
  readonly onFansub: () => void
  readonly onExport: () => void
  readonly updatePending: boolean
  readonly refreshPending: boolean
}

const sectionLabelStyle: React.CSSProperties = {
  fontSize: '10px',
  fontWeight: 600,
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  marginBottom: '8px',
}

const buttonBaseStyle: React.CSSProperties = {
  fontSize: '11px',
  padding: '4px 10px',
  borderRadius: '4px',
  cursor: 'pointer',
}

export function SeriesSettingsPanel({
  series,
  showGlossary,
  hasFansubOverride,
  isExtracting,
  extractProgress,
  onToggleGlossary,
  onToggleAbsoluteOrder,
  onRefreshAnidb,
  onExtract,
  onCleanup,
  onFansub,
  onExport,
  updatePending,
  refreshPending,
}: SeriesSettingsPanelProps) {
  return (
    <div
      style={{
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        marginBottom: '16px',
      }}
    >
      {/* Language section */}
      <div>
        <div style={sectionLabelStyle}>Language</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
          {series.profile_name && (
            <span
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                backgroundColor: 'var(--accent-bg)',
                color: 'var(--accent)',
                border: '1px solid var(--accent)',
                fontWeight: 600,
              }}
            >
              {series.profile_name}
            </span>
          )}
          {series.target_language_names?.map((name: string) => (
            <span
              key={name}
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {name}
            </span>
          ))}
          {series.source_language_name && (
            <span
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                backgroundColor: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
                fontStyle: 'italic',
              }}
            >
              src: {series.source_language_name}
            </span>
          )}
        </div>
      </div>

      {/* Subtitles section */}
      <div>
        <div style={sectionLabelStyle}>Subtitles</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          {/* Glossary toggle */}
          <button
            onClick={onToggleGlossary}
            style={{
              ...buttonBaseStyle,
              backgroundColor: showGlossary ? 'var(--accent-bg)' : 'var(--bg-elevated)',
              color: showGlossary ? 'var(--accent)' : 'var(--text-secondary)',
              border: showGlossary ? '1px solid var(--accent)' : '1px solid var(--border)',
            }}
          >
            📖 Glossary
          </button>

          {/* Absolute order toggle — field is `absolute_order` on SeriesDetail */}
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              color: 'var(--text-secondary)',
              cursor: updatePending ? 'default' : 'pointer',
              opacity: updatePending ? 0.6 : 1,
            }}
          >
            <input
              type="checkbox"
              checked={series.absolute_order ?? false}
              disabled={updatePending}
              onChange={(e) => onToggleAbsoluteOrder(e.target.checked)}
            />
            Absolute Order
          </label>

          {/* AniDB refresh — only shown when absolute order is enabled */}
          {series.absolute_order && (
            <button
              onClick={onRefreshAnidb}
              disabled={refreshPending}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                opacity: refreshPending ? 0.6 : 1,
                cursor: refreshPending ? 'default' : 'pointer',
              }}
            >
              🔄 AniDB Refresh
            </button>
          )}
        </div>
      </div>

      {/* Tools section */}
      <div>
        <div style={sectionLabelStyle}>Tools</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
          {/* Untertitel exportieren */}
          <Tooltip content="Alle Sidecar-Untertitel dieser Serie als ZIP-Datei herunterladen — praktisch als Backup oder zur Weitergabe.">
            <button
              onClick={onExport}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
            >
              📦 Untertitel exportieren
            </button>
          </Tooltip>

          {/* Embedded extrahieren */}
          <Tooltip content="Eingebettete Untertitel-Streams aus allen Episoden als Sidecar-Dateien speichern und aus dem Videocontainer entfernen.">
            <button
              onClick={onExtract}
              disabled={isExtracting}
              style={{
                ...buttonBaseStyle,
                backgroundColor: isExtracting ? 'var(--accent-bg)' : 'var(--bg-elevated)',
                color: isExtracting ? 'var(--accent)' : 'var(--text-secondary)',
                border: isExtracting ? '1px solid var(--accent-dim)' : '1px solid var(--border)',
                opacity: isExtracting ? 0.6 : 1,
                cursor: isExtracting ? 'default' : 'pointer',
              }}
            >
              {isExtracting
                ? `Extrahiere… ${extractProgress ? `${extractProgress.current}/${extractProgress.total}` : ''}`
                : '🎵 Embedded extrahieren'
              }
            </button>
          </Tooltip>

          {/* Sidecar bereinigen */}
          <Tooltip content="Sidecar-Untertitel nach Sprache oder Format filtern und in den Papierkorb verschieben (wiederherstellbar).">
            <button
              onClick={onCleanup}
              style={{
                ...buttonBaseStyle,
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)',
                cursor: 'pointer',
              }}
            >
              🧹 Sidecar bereinigen
            </button>
          </Tooltip>

          {/* Fansub-Override */}
          <Tooltip content="Bevorzugten Fansub-Anbieter für diese Serie festlegen. Überschreibt die globale Anbieter-Priorität.">
            <button
              onClick={onFansub}
              style={{
                ...buttonBaseStyle,
                backgroundColor: hasFansubOverride ? 'var(--accent-bg)' : 'var(--bg-elevated)',
                color: hasFansubOverride ? 'var(--accent)' : 'var(--text-secondary)',
                border: hasFansubOverride ? '1px solid var(--accent)' : '1px solid var(--border)',
                fontWeight: hasFansubOverride ? 600 : 400,
                cursor: 'pointer',
              }}
            >
              🎭 Fansub-Override{hasFansubOverride ? ' ✓' : ''}
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}
