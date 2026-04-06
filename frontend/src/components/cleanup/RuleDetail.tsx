import { Play, Eye, Trash2, Power } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CleanupRule } from '@/types/system'
import { LanguageFilterConfig } from './LanguageFilterConfig'
import { FormatUpgradeConfig } from './FormatUpgradeConfig'
import { SchedulePicker } from './SchedulePicker'

interface PreviewResult {
  would_delete?: number
  would_keep?: number
  [key: string]: number | undefined
}

interface RuleDetailProps {
  rule: CleanupRule
  previewResult: PreviewResult | null
  isRunning: boolean
  isPreviewing: boolean
  onRun: () => void
  onPreview: () => void
  onDelete: () => void
  onUpdate: (patch: Partial<CleanupRule>) => void
}

const TYPE_DESCRIPTIONS: Record<string, string> = {
  language_filter: 'Löscht Sidecar-Dateien in nicht erlaubten Sprachen',
  format_upgrade: 'Löscht SRT wenn ASS für dieselbe Episode existiert',
  orphan_files: 'Löscht Subtitle-Sidecars ohne zugehörige Videodatei auf Disk',
  orphan_db: 'Entfernt DB-Einträge deren Datei auf Disk fehlt',
  dedup: 'Findet und löscht doppelte Untertitel-Dateien',
}

const TYPE_ICONS: Record<string, string> = {
  language_filter: '🌐',
  format_upgrade: '⬆️',
  orphan_files: '🗑️',
  orphan_db: '🗄️',
  dedup: '🔍',
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

function ConfigSection({
  title,
  icon,
  children,
}: {
  title: string
  icon: string
  children: React.ReactNode
}) {
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div
        className="flex items-center gap-2.5 px-4 py-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <span
          className="flex items-center justify-center rounded-md text-sm"
          style={{ width: 26, height: 26, background: 'var(--accent-bg)' }}
        >
          {icon}
        </span>
        <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {title}
        </span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  )
}

export function RuleDetail({
  rule,
  previewResult,
  isRunning,
  isPreviewing,
  onRun,
  onPreview,
  onDelete,
  onUpdate,
}: RuleDetailProps) {
  const { t } = useTranslation('common')
  const config = rule.config_json as Record<string, unknown>

  const updateConfig = (patch: Record<string, unknown>) =>
    onUpdate({ config_json: { ...config, ...patch } })

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center rounded-xl text-2xl flex-shrink-0"
            style={{ width: 44, height: 44, background: 'var(--accent-bg)' }}
          >
            {TYPE_ICONS[rule.rule_type] ?? '⚙️'}
          </div>
          <div>
            <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
              {rule.name}
            </div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {TYPE_DESCRIPTIONS[rule.rule_type] ?? rule.rule_type}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <button
            onClick={() => onUpdate({ enabled: !rule.enabled })}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{
              border: '1px solid var(--border)',
              color: rule.enabled ? 'var(--success)' : 'var(--text-muted)',
            }}
          >
            <Power size={12} />
            {rule.enabled ? 'Aktiv' : 'Deaktiviert'}
          </button>
          <button
            onClick={onPreview}
            disabled={isPreviewing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            <Eye size={12} />
            {isPreviewing ? 'Lädt...' : 'Vorschau'}
          </button>
          <button
            onClick={onRun}
            disabled={isRunning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            <Play size={12} />
            {isRunning ? 'Läuft...' : 'Jetzt ausführen'}
          </button>
          <button
            onClick={onDelete}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs"
            style={{ border: '1px solid var(--error-dim, #3a1a1a)', color: 'var(--error)' }}
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Last run bar */}
      {rule.last_run_at && (
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <span
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: 'var(--success)' }}
          />
          <span style={{ color: 'var(--success)' }}>{t('cleanup_detail.last_run_success')}</span>
          <span className="ml-auto" style={{ color: 'var(--text-muted)' }}>
            {new Date(rule.last_run_at).toLocaleString('de-DE')}
          </span>
        </div>
      )}

      {/* Type-specific config */}
      {rule.rule_type === 'language_filter' && (
        <ConfigSection title={t('cleanup_detail.allowed_langs')} icon="🌐">
          <LanguageFilterConfig
            value={(config.keep_languages as string[]) ?? []}
            onChange={(langs) => updateConfig({ keep_languages: langs })}
          />
        </ConfigSection>
      )}

      {rule.rule_type === 'format_upgrade' && (
        <ConfigSection title={t('cleanup_detail.format_pref')} icon="📄">
          <FormatUpgradeConfig
            value={(config.keep_format as 'any' | 'ass' | 'srt') ?? 'any'}
            onChange={(fmt) => updateConfig({ keep_format: fmt })}
          />
        </ConfigSection>
      )}

      {/* Schedule (all types) */}
      <ConfigSection title={t('cleanup_detail.schedule')} icon="🕐">
        <SchedulePicker value={rule.schedule} onChange={(s) => onUpdate({ schedule: s })} />
      </ConfigSection>

      {/* Preview result */}
      {previewResult && (
        <ConfigSection title={t('cleanup_detail.preview')} icon="👁️">
          <div className="space-y-1.5">
            {Object.entries(previewResult).map(([key, val]) => (
              <div key={key} className="flex justify-between text-xs">
                <span style={{ color: 'var(--text-muted)' }}>{key}</span>
                <span
                  style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}
                >
                  {typeof val === 'number' && key.includes('byte') ? formatBytes(val) : val}
                </span>
              </div>
            ))}
          </div>
        </ConfigSection>
      )}
    </div>
  )
}
