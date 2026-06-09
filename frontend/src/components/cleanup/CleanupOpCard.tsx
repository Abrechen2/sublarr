/**
 * CleanupOpCard — expandable card for a single fixed cleanup operation.
 *
 * Each of the 5 cleanup types (language_filter, format_upgrade, orphan_files,
 * orphan_db, old_backups) is represented by one card. The card is always
 * visible; users toggle it on/off and configure it inline.
 */
import { useState } from 'react'
import { Play, Eye, ChevronDown, ChevronUp, Trash2, CheckCircle2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CleanupRule } from '@/types/system'
import { useRunCleanupRule, useRulePreview } from '@/hooks/useSystemApi'
import { LanguageFilterConfig } from './LanguageFilterConfig'
import { FormatUpgradeConfig } from './FormatUpgradeConfig'
import { SchedulePicker } from './SchedulePicker'
import { toast } from '@/components/shared/Toast'

// ─── Types ────────────────────────────────────────────────────────────────────

interface PreviewExample {
  path: string
  size_bytes?: number
  reason?: string
  // foreign_tracks preview shape
  tracks?: number
  langs?: string[]
}

interface PreviewResult {
  would_delete?: number
  would_keep?: number
  // foreign_tracks preview shape
  would_strip_files?: number
  would_strip_tracks?: number
  examples?: PreviewExample[]
}

export interface OpMeta {
  ruleType: string
  Icon: React.ElementType
  iconColor: string
  iconBg: string
  title: string
  description: string
  defaultName: string
  /** Seed config applied when the rule is first created (default: {}). */
  defaultConfig?: Record<string, unknown>
}

interface CleanupOpCardProps {
  meta: OpMeta
  rule: CleanupRule | null
  onToggle: (enabled: boolean) => void
  onUpdate: (patch: Partial<CleanupRule>) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

// ─── Preview Panel ────────────────────────────────────────────────────────────

function PreviewPanel({
  result,
  onClose,
}: {
  result: PreviewResult
  onClose: () => void
}) {
  const willDelete = result.would_delete ?? result.would_strip_files ?? 0
  const willKeep = result.would_keep
  const examples = result.examples ?? []
  const total = willDelete + (willKeep ?? 0)
  const pct = total > 0 ? Math.round((willDelete / total) * 100) : 0
  const stripTracks = result.would_strip_tracks

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: '1px solid var(--border)', marginTop: 20 }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-3"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}
      >
        <div className="flex items-center gap-2.5">
          <Eye size={13} style={{ color: 'var(--text-muted)' }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            Vorschau — Trockenlauf
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            keine echte Änderung
          </span>
          <button
            onClick={onClose}
            className="text-xs"
            style={{ color: 'var(--text-muted)' }}
          >
            ✕
          </button>
        </div>
      </div>

      <div className="p-5 space-y-5" style={{ background: 'var(--bg-elevated)' }}>
        {/* Summary tiles */}
        <div className="grid grid-cols-2 gap-4">
          <div
            className="rounded-lg px-4 py-5 text-center"
            style={{
              background: 'color-mix(in srgb, var(--error) 8%, transparent)',
              border: '1px solid color-mix(in srgb, var(--error) 25%, transparent)',
            }}
          >
            <div
              className="text-3xl font-bold tabular-nums"
              style={{ fontFamily: 'var(--font-mono)', color: 'var(--error)' }}
            >
              {willDelete}
            </div>
            <div className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              {stripTracks !== undefined
                ? `Dateien (${stripTracks} Spuren würden entfernt)`
                : 'würden gelöscht'}
            </div>
          </div>
          {willKeep !== undefined && (
            <div
              className="rounded-lg px-4 py-5 text-center"
              style={{
                background: 'color-mix(in srgb, var(--success) 8%, transparent)',
                border: '1px solid color-mix(in srgb, var(--success) 25%, transparent)',
              }}
            >
              <div
                className="text-3xl font-bold tabular-nums"
                style={{ fontFamily: 'var(--font-mono)', color: 'var(--success)' }}
              >
                {willKeep}
              </div>
              <div className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                bleiben erhalten
              </div>
            </div>
          )}
        </div>

        {/* Progress bar */}
        {willDelete > 0 && total > 0 && (
          <div>
            <div
              className="flex justify-between text-xs mb-2"
              style={{ color: 'var(--text-muted)' }}
            >
              <span>{pct}% würden entfernt</span>
              <span>{total} gesamt</span>
            </div>
            <div
              className="rounded-full overflow-hidden"
              style={{ height: 7, background: 'var(--bg-primary)' }}
            >
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, background: 'var(--error)' }}
              />
            </div>
          </div>
        )}

        {/* File list */}
        {examples.length > 0 && (
          <div>
            <div
              className="text-[10px] font-semibold uppercase tracking-wider mb-3"
              style={{ color: 'var(--text-muted)' }}
            >
              Beispiele ({examples.length}
              {willDelete > examples.length ? ` von ${willDelete}` : ''})
            </div>
            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--border)' }}>
              {examples.map((ex, i) => {
                const filename = ex.path.split(/[\\/]/).pop() ?? ex.path
                const dir = ex.path.split(/[\\/]/).slice(0, -1).join('/') || '/'
                return (
                  <div
                    key={i}
                    className="flex items-center gap-3 px-4 py-3"
                    style={{
                      borderBottom: i < examples.length - 1 ? '1px solid var(--border)' : undefined,
                      background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,.015)',
                    }}
                  >
                    <Trash2 size={12} style={{ color: 'var(--error)', flexShrink: 0 }} />
                    <div className="flex-1 min-w-0">
                      <div
                        className="text-xs font-medium truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {filename}
                      </div>
                      <div
                        className="text-[11px] truncate mt-0.5"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {dir}
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      {(ex.size_bytes ?? 0) > 0 && (
                        <span
                          className="text-[11px] tabular-nums"
                          style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}
                        >
                          {formatBytes(ex.size_bytes ?? 0)}
                        </span>
                      )}
                      {ex.langs && ex.langs.length > 0 && (
                        <span
                          className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded"
                          style={{
                            background: 'color-mix(in srgb, var(--error) 12%, transparent)',
                            color: 'var(--error)',
                          }}
                        >
                          {ex.langs.join(', ')}
                          {ex.tracks ? ` (${ex.tracks})` : ''}
                        </span>
                      )}
                      {ex.reason && (
                        <span
                          className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded"
                          style={{
                            background: 'color-mix(in srgb, var(--error) 12%, transparent)',
                            color: 'var(--error)',
                          }}
                        >
                          {ex.reason}
                        </span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            {willDelete > examples.length && (
              <div className="text-xs text-center pt-3" style={{ color: 'var(--text-muted)' }}>
                + {willDelete - examples.length} weitere Dateien nicht angezeigt
              </div>
            )}
          </div>
        )}

        {willDelete === 0 && (
          <div className="flex items-center justify-center gap-2 py-3 text-sm" style={{ color: 'var(--success)' }}>
            <CheckCircle2 size={15} />
            Keine Dateien würden gelöscht
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Card ────────────────────────────────────────────────────────────────

export function CleanupOpCard({ meta, rule, onToggle, onUpdate }: CleanupOpCardProps) {
  const { t: tc } = useTranslation('common')
  const { t } = useTranslation('common')
  const [expanded, setExpanded] = useState(false)
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null)

  const runRule = useRunCleanupRule()
  const rulePreview = useRulePreview()

  const { Icon } = meta
  const config = (rule?.config_json ?? {}) as Record<string, unknown>
  const enabled = rule?.enabled ?? false

  const updateConfig = (patch: Record<string, unknown>) =>
    onUpdate({ config_json: { ...config, ...patch } })

  const handleHeaderClick = () => {
    setExpanded((v) => !v)
  }

  const handleToggleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!enabled && !expanded) setExpanded(true)
    onToggle(!enabled)
  }

  const handleRun = () => {
    if (!rule) return
    runRule.mutate(rule.id, {
      onSuccess: () => toast(t('cleanup_detail.run_success', 'Ausgeführt'), 'success'),
      onError: () => toast(t('cleanup_detail.run_error', 'Fehler beim Ausführen'), 'error'),
    })
  }

  const handlePreview = () => {
    if (!rule) return
    rulePreview.mutate(rule.id, {
      onSuccess: (data: { preview: PreviewResult }) => {
        setPreviewResult(data.preview)
        if (!expanded) setExpanded(true)
      },
      onError: () => toast(t('cleanup_detail.preview_error', 'Vorschau fehlgeschlagen'), 'error'),
    })
  }

  return (
    <div
      className="rounded-xl overflow-hidden transition-all"
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${enabled
          ? 'color-mix(in srgb, var(--accent) 28%, var(--border))'
          : 'var(--border)'
        }`,
      }}
    >
      {/* ── Card header (always visible) ── */}
      <div
        className="flex items-center gap-4 px-5 py-4 cursor-pointer select-none"
        onClick={handleHeaderClick}
        style={{ opacity: enabled ? 1 : 0.65 }}
      >
        {/* Icon */}
        <div
          className="flex items-center justify-center rounded-xl flex-shrink-0"
          style={{ width: 40, height: 40, background: meta.iconBg }}
        >
          <Icon size={18} style={{ color: meta.iconColor }} />
        </div>

        {/* Title + description */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {meta.title}
          </div>
          <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {meta.description}
          </div>
        </div>

        {/* Last run timestamp — shown when collapsed */}
        {!expanded && rule?.last_run_at && (
          <div className="text-[11px] text-right flex-shrink-0 hidden sm:block" style={{ color: 'var(--text-muted)' }}>
            <div>{tc('ui.last')}</div>
            <div>{new Date(rule.last_run_at).toLocaleDateString('de-DE')}</div>
          </div>
        )}

        {/* Toggle */}
        <div
          className="flex items-center gap-2 flex-shrink-0"
          onClick={handleToggleClick}
          title={enabled ? 'Deaktivieren' : 'Aktivieren'}
        >
          <span
            className="text-xs font-medium"
            style={{ color: enabled ? 'var(--success)' : 'var(--text-muted)' }}
          >
            {enabled ? 'Aktiv' : 'Inaktiv'}
          </span>
          <div
            className="relative flex-shrink-0 rounded-full transition-colors"
            style={{
              width: 36,
              height: 20,
              background: enabled ? 'var(--accent)' : 'var(--border)',
            }}
          >
            <div
              className="absolute top-[3px] rounded-full bg-white transition-transform"
              style={{
                width: 14,
                height: 14,
                left: 3,
                transform: enabled ? 'translateX(16px)' : 'translateX(0)',
                boxShadow: '0 1px 3px rgba(0,0,0,.3)',
              }}
            />
          </div>
        </div>

        {/* Chevron */}
        <div className="flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
          {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </div>
      </div>

      {/* ── Expanded body ── */}
      {expanded && (
        <div
          className="px-5 py-5"
          style={{ borderTop: '1px solid var(--border)', background: 'var(--bg-primary)' }}
        >
          {/* Config + schedule row */}
          <div className="flex gap-8 flex-wrap">
            {/* Type-specific config */}
            {meta.ruleType === 'language_filter' && (
              <div className="flex-1 min-w-[220px]">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Sprachen behalten
                </div>
                <LanguageFilterConfig
                  value={(config.keep_languages as string[]) ?? []}
                  onChange={(langs) => updateConfig({ keep_languages: langs })}
                />
              </div>
            )}

            {meta.ruleType === 'foreign_tracks' && (
              <div className="flex-1 min-w-[220px]">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Sprachen behalten
                </div>
                <LanguageFilterConfig
                  value={(config.keep_languages as string[]) ?? ['de', 'en']}
                  onChange={(langs) => updateConfig({ keep_languages: langs })}
                />
                <label
                  className="flex items-center gap-2 mt-3 text-sm cursor-pointer"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <input
                    type="checkbox"
                    checked={(config.keep_und as boolean) ?? true}
                    onChange={(e) => updateConfig({ keep_und: e.target.checked })}
                  />
                  Unbestimmte Sprache (und) behalten
                </label>
              </div>
            )}

            {meta.ruleType === 'format_upgrade' && (
              <div className="flex-1 min-w-[220px]">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Bevorzugtes Format
                </div>
                <FormatUpgradeConfig
                  value={(config.keep_format as 'any' | 'ass' | 'srt') ?? 'any'}
                  onChange={(fmt) => updateConfig({ keep_format: fmt })}
                />
              </div>
            )}

            {meta.ruleType === 'old_backups' && (
              <div className="flex-1 min-w-[160px]">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Aufbewahrung (Tage)
                </div>
                <input
                  type="number"
                  min={1}
                  value={(config.retention_days as number) ?? 7}
                  onChange={(e) =>
                    updateConfig({ retention_days: Math.max(1, parseInt(e.target.value, 10) || 7) })
                  }
                  className="px-3 py-2 rounded-lg text-sm focus:outline-none"
                  style={{
                    width: 110,
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
            )}

            {meta.ruleType === 'old_subtitle_baks' && (
              <div className="flex-1 min-w-[160px]">
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: 'var(--text-muted)' }}
                >
                  Aufbewahrung (Tage)
                </div>
                <input
                  type="number"
                  min={0}
                  value={(config.retention_days as number) ?? 30}
                  onChange={(e) =>
                    updateConfig({
                      retention_days: Math.max(0, parseInt(e.target.value, 10) || 30),
                    })
                  }
                  className="px-3 py-2 rounded-lg text-sm focus:outline-none"
                  style={{
                    width: 110,
                    background: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-primary)',
                  }}
                  title="0 = keep forever (orphans still purged immediately)"
                />
              </div>
            )}

            {/* Schedule — always shown */}
            <div className="flex-1 min-w-[220px]">
              <div
                className="text-[10px] font-semibold uppercase tracking-wider mb-3"
                style={{ color: 'var(--text-muted)' }}
              >
                Zeitplan
              </div>
              <SchedulePicker
                value={rule?.schedule ?? 'manual'}
                onChange={(s) => onUpdate({ schedule: s })}
              />
            </div>
          </div>

          {/* Action row */}
          <div
            className="flex items-center gap-3 mt-5 pt-5"
            style={{ borderTop: '1px solid var(--border)' }}
          >
            {meta.ruleType !== 'old_subtitle_baks' && meta.ruleType !== 'old_backups' && (
              <button
                onClick={handlePreview}
                disabled={!rule || rulePreview.isPending}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-40 transition-opacity"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                <Eye size={13} />
                {rulePreview.isPending ? 'Lädt…' : 'Vorschau'}
              </button>
            )}

            <button
              onClick={handleRun}
              disabled={!rule || runRule.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-40 transition-opacity"
              style={{ background: 'var(--accent)', color: '#000' }}
            >
              <Play size={13} />
              {runRule.isPending ? 'Läuft…' : 'Jetzt ausführen'}
            </button>

            {!rule && (
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Zuerst aktivieren
              </span>
            )}

            {rule?.last_run_at && (
              <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>
                Zuletzt: {new Date(rule.last_run_at).toLocaleString('de-DE')}
              </span>
            )}
          </div>

          {/* Inline preview result */}
          {previewResult && (
            <PreviewPanel result={previewResult} onClose={() => setPreviewResult(null)} />
          )}
        </div>
      )}
    </div>
  )
}
