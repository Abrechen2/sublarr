import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'

const numInputStyle = {
  backgroundColor: 'var(--bg-primary)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
  borderRadius: '0.375rem',
  padding: '0.375rem 0.75rem',
  fontSize: '0.8125rem',
  outline: 'none',
  width: '90px',
}

/**
 * DubtitleSettings — UI for the dubtitle-detection config group, which was
 * previously config/env-only. Maps to dubtitle_detection, dubtitle_min_score,
 * dubtitle_min_margin, dubtitle_auto_min_cues and dubtitle_verify_on_download.
 */
export function DubtitleSettings() {
  const { t } = useTranslation('settings')
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const cfg = config as Record<string, unknown> | undefined

  const detection = String(cfg?.dubtitle_detection ?? 'false') === 'true'
  const verifyOnDownload = String(cfg?.dubtitle_verify_on_download ?? 'false') === 'true'
  const minScore = Number(cfg?.dubtitle_min_score ?? 0.55)
  const minMargin = Number(cfg?.dubtitle_min_margin ?? 0.15)
  const autoMinCues = Number(cfg?.dubtitle_auto_min_cues ?? 70)

  const setNum = (key: string, raw: string, lo: number, hi: number, round = false) => {
    const n = Number(raw)
    if (!Number.isFinite(n)) return
    const v = Math.min(hi, Math.max(lo, round ? Math.round(n) : n))
    updateConfig.mutate({ [key]: v })
  }

  return (
    <SettingsSection
      title={t('dubtitle_page.title', 'Dubtitle Detection')}
      description={t(
        'dubtitle_page.description',
        'Identify (and optionally verify) the English "dubtitle" among the multiple English tracks anime files ship.',
      )}
      icon={<Languages size={16} style={{ color: 'var(--accent)' }} />}
    >
      <SettingRow
        label={t('dubtitle_page.detection_label', 'Dubtitle detection')}
        description={t(
          'dubtitle_page.detection_desc',
          'Detect which English track is the dubtitle. The track-panel button always works; this toggle governs the nightly sweep that flags it automatically.',
        )}
      >
        <div data-testid="toggle-dubtitle-detection">
          <Toggle
            checked={detection}
            onChange={(v) => updateConfig.mutate({ dubtitle_detection: String(v) })}
          />
        </div>
      </SettingRow>

      <SettingRow
        label={t('dubtitle_page.verify_label', 'Verify downloads against the dub')}
        description={t(
          'dubtitle_page.verify_desc',
          'After downloading an English subtitle for an episode that has English dub audio, score it against the dub; a confident mismatch is kept but flagged in the logs. Requires Whisper; falls back to keep when unavailable.',
        )}
      >
        <div data-testid="toggle-dubtitle-verify">
          <Toggle
            checked={verifyOnDownload}
            onChange={(v) => updateConfig.mutate({ dubtitle_verify_on_download: String(v) })}
          />
        </div>
      </SettingRow>

      {detection && (
        <>
          <SettingRow
            label={t('dubtitle_page.min_score_label', 'Minimum match score')}
            description={t(
              'dubtitle_page.min_score_desc',
              'Tier-2 acceptance threshold (0-1). A track must score at least this against the dub audio. Lower it if real dubtitles are being missed; raise it to be stricter.',
            )}
          >
            <input
              data-testid="input-dubtitle-min-score"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minScore}
              onChange={(e) => setNum('dubtitle_min_score', e.target.value, 0, 1)}
              style={numInputStyle}
            />
          </SettingRow>

          <SettingRow
            label={t('dubtitle_page.min_margin_label', 'Minimum margin')}
            description={t(
              'dubtitle_page.min_margin_desc',
              'Unattended only (0-1). The winner must beat the runner-up by at least this much, so two near-tied tracks are never auto-flagged on a coin-flip.',
            )}
          >
            <input
              data-testid="input-dubtitle-min-margin"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={minMargin}
              onChange={(e) => setNum('dubtitle_min_margin', e.target.value, 0, 1)}
              style={numInputStyle}
            />
          </SettingRow>

          <SettingRow
            label={t('dubtitle_page.auto_cues_label', 'Auto cue floor')}
            description={t(
              'dubtitle_page.auto_cues_desc',
              'Unattended only. A track needs at least this many cues to be considered during the scheduled sweep, so a sparse track cannot fluke a match.',
            )}
          >
            <input
              data-testid="input-dubtitle-auto-cues"
              type="number"
              min={1}
              step={1}
              value={autoMinCues}
              onChange={(e) => setNum('dubtitle_auto_min_cues', e.target.value, 1, 100000, true)}
              style={numInputStyle}
            />
          </SettingRow>
        </>
      )}
    </SettingsSection>
  )
}
