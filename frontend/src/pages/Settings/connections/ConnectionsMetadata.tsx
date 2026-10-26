/**
 * ConnectionsMetadata — Metadata API keys configuration.
 *
 * Extracted from ConnectionsSettings.tsx (pure file split, no functional changes).
 * All config keys (tmdb_api_key, tvdb_api_key, tvdb_pin, metadata_cache_ttl_days)
 * and design patterns are unchanged.
 *
 * Note: ffmpeg_timeout was moved to Automation → Search & Scan (Advanced).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Database } from 'lucide-react'
import { Eye, EyeOff } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { SettingsSection } from '@/components/settings/SettingsSection'

// ─── MetadataApiKeysSection ──────────────────────────────────────────────────

// Key rows stack label above the controls below md so the input can shrink to the
// available width; from md up they keep the label left, 260 px input right layout.
const KEY_ROW_CLASS =
  'flex flex-col items-stretch gap-2 py-3 md:flex-row md:items-center md:justify-between'
const KEY_CONTROLS_CLASS = 'flex min-w-0 items-center gap-1.5'
const KEY_INPUT_CLASS = 'focus:outline-none min-w-0 w-full md:w-[260px]'

function MetadataApiKeysSection() {
  const { t } = useTranslation('common')
  const { data: configData } = useConfig()
  const updateConfig = useUpdateConfig()

  const cfg = configData as Record<string, unknown> | undefined

  const [tmdbKey, setTmdbKey] = useState(() => String(cfg?.tmdb_api_key ?? ''))
  const [tvdbKey, setTvdbKey] = useState(() => String(cfg?.tvdb_api_key ?? ''))
  const [tvdbPin, setTvdbPin] = useState(() => String(cfg?.tvdb_pin ?? ''))
  const [cacheTtl, setCacheTtl] = useState(() => String(cfg?.metadata_cache_ttl_days ?? '7'))

  const [showTmdb, setShowTmdb] = useState(false)
  const [showTvdb, setShowTvdb] = useState(false)
  const [showPin, setShowPin]   = useState(false)

  const handleSave = () => {
    updateConfig.mutate(
      {
        tmdb_api_key:            tmdbKey,
        tvdb_api_key:            tvdbKey,
        tvdb_pin:                tvdbPin,
        metadata_cache_ttl_days: cacheTtl,
      },
      {
        onSuccess: () => toast(t('settings:connections_metadata.saved')),
        onError:   () => toast(t('settings:connections_metadata.save_failed'), 'error'),
      },
    )
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-elevated)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
    padding: '7px 12px',
    borderRadius: '6px',
    flex: 1,
  } as const

  const numberInputStyle = {
    ...inputStyle,
    width: '120px',
    flex: 'none',
  } as const

  return (
    <div data-testid="metadata-api-keys-section" className="space-y-0">

      {/* TMDB */}
      <div
        className={KEY_ROW_CLASS}
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tmdb-api-key"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings:connections_metadata.tmdb_api_key')}
        </label>
        <div className={KEY_CONTROLS_CLASS}>
          <input
            id="tmdb-api-key"
            data-testid="metadata-tmdb-api-key"
            type={showTmdb ? 'text' : 'password'}
            value={tmdbKey}
            onChange={(e) => setTmdbKey(e.target.value)}
            placeholder={t('settings:connections_metadata.tmdb_placeholder')}
            className={KEY_INPUT_CLASS}
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => setShowTmdb((v) => !v)}
            className="p-1.5 rounded shrink-0"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showTmdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB API Key */}
      <div
        className={KEY_ROW_CLASS}
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tvdb-api-key"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings:connections_metadata.tvdb_api_key')}
        </label>
        <div className={KEY_CONTROLS_CLASS}>
          <input
            id="tvdb-api-key"
            data-testid="metadata-tvdb-api-key"
            type={showTvdb ? 'text' : 'password'}
            value={tvdbKey}
            onChange={(e) => setTvdbKey(e.target.value)}
            placeholder={t('settings:connections_metadata.tvdb_placeholder')}
            className={KEY_INPUT_CLASS}
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => setShowTvdb((v) => !v)}
            className="p-1.5 rounded shrink-0"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showTvdb ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* TVDB PIN */}
      <div
        className={KEY_ROW_CLASS}
        style={{ borderBottom: '1px solid rgba(42,46,56,0.5)' }}
      >
        <label
          htmlFor="tvdb-pin"
          className="text-[13px] font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {t('settings:connections_metadata.tvdb_pin')}
        </label>
        <div className={KEY_CONTROLS_CLASS}>
          <input
            id="tvdb-pin"
            data-testid="metadata-tvdb-pin"
            type={showPin ? 'text' : 'password'}
            value={tvdbPin}
            onChange={(e) => setTvdbPin(e.target.value)}
            placeholder={t('settings:connections_metadata.subscriber_pin')}
            className={KEY_INPUT_CLASS}
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => setShowPin((v) => !v)}
            className="p-1.5 rounded shrink-0"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-muted)',
              backgroundColor: 'var(--bg-primary)',
            }}
          >
            {showPin ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
      </div>

      {/* Metadata cache TTL */}
      <div className="flex items-center justify-between gap-2 py-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <label
            htmlFor="metadata-cache-ttl"
            className="text-[13px] font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            {t('settings:connections_metadata.cache_ttl')}
          </label>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {t('settings:connections_metadata.cache_ttl_desc')}
          </span>
        </div>
        <input
          id="metadata-cache-ttl"
          data-testid="metadata-cache-ttl"
          type="number"
          min={1}
          value={cacheTtl}
          onChange={(e) => setCacheTtl(e.target.value)}
          className="focus:outline-none"
          style={numberInputStyle}
        />
      </div>

      {/* Save */}
      <div className="flex justify-end pt-2">
        <button
          data-testid="metadata-save-btn"
          type="button"
          onClick={handleSave}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {t('settings:connections_metadata.save')}
        </button>
      </div>
    </div>
  )
}

// ─── MetadataSectionWrapper (exported) ──────────────────────────────────────

export function MetadataSectionWrapper() {
  const { t } = useTranslation('settings')
  return (
    <SettingsSection
      title={t('connections_metadata.title')}
      description={t('connections_metadata.section_desc')}
      icon={<Database size={16} style={{ color: 'var(--accent)' }} />}
    >
      <div className="py-1">
        <MetadataApiKeysSection />
      </div>
    </SettingsSection>
  )
}
