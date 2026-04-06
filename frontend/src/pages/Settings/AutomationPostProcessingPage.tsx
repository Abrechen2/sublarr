import { useTranslation } from 'react-i18next'
import { Workflow } from 'lucide-react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { SettingsSection } from '@/components/settings/SettingsSection'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, boolVal } from '@/lib/configUtils'
import { settingsInputStyle } from '@/styles/settingsShared'

const inputStyle: React.CSSProperties = { ...settingsInputStyle, width: '220px', outline: 'none' }

function SectionSkeleton() {
  return (
    <div data-testid="section-skeleton" className="animate-pulse space-y-3 py-2">
      {[...Array(3)].map((_, i) => (
        <div
          key={i}
          className="h-8 rounded"
          style={{ backgroundColor: 'var(--bg-surface-hover)', width: i === 0 ? '70%' : '100%' }}
        />
      ))}
    </div>
  )
}

function ProcessingPipelineAdvancedContent() {
  const { t: tS } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="processing-pipeline-advanced-content">
      <FormGroup
        label={tS('automation_page.sync_threshold')}
        hint={tS('automation_page.sync_threshold_hint')}
        htmlFor="auto-process-sync-threshold"
        advanced
        data-testid="form-group-auto-process-sync-threshold"
      >
        <input
          id="auto-process-sync-threshold"
          type="number"
          data-testid="input-auto-process-sync-threshold"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'auto_process_sync_threshold', '80')}
          onChange={(e) => save({ auto_process_sync_threshold: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          max={100}
          placeholder="80"
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.sync_fallback_engine')}
        hint={tS('automation_page.sync_fallback_engine_hint')}
        htmlFor="auto-process-sync-fallback-engine"
        advanced
        data-testid="form-group-auto-process-sync-fallback-engine"
      >
        <select
          id="auto-process-sync-fallback-engine"
          data-testid="select-auto-process-sync-fallback-engine"
          style={{ ...inputStyle, maxWidth: '160px', cursor: 'pointer' }}
          value={strVal(config, 'auto_process_sync_fallback_engine', 'ffsubsync')}
          onChange={(e) => save({ auto_process_sync_fallback_engine: e.target.value })}
          disabled={updateConfig.isPending}
        >
          <option value="auto">auto</option>
          <option value="alass">alass</option>
          <option value="ffsubsync">ffsubsync</option>
        </select>
      </FormGroup>
    </div>
  )
}

function ProcessingPipelineContent() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="processing-pipeline-content">
      <FormGroup
        label={t('settings.automation.pipeline.autoTranslate', 'Auto-Translate')}
        hint={t(
          'settings.automation.pipeline.autoTranslateHint',
          'Automatically translate downloaded subtitles to the target language.',
        )}
        data-testid="form-group-wanted-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'wanted_auto_translate', false)}
          onChange={(v) => save({ wanted_auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoSync', 'Auto-Sync')}
        hint={t(
          'settings.automation.pipeline.autoSyncHint',
          'Automatically synchronise subtitles to video timing after download.',
        )}
        data-testid="form-group-auto-sync-after-download"
      >
        <Toggle
          checked={boolVal(config, 'auto_sync_after_download', false)}
          onChange={(v) => save({ auto_sync_after_download: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('settings.automation.pipeline.autoCleanup', 'Auto-Cleanup')}
        hint={t(
          'settings.automation.pipeline.autoCleanupHint',
          'Remove duplicate and redundant subtitle files automatically after extract.',
        )}
        data-testid="form-group-auto-cleanup-after-extract"
      >
        <Toggle
          checked={boolVal(config, 'auto_cleanup_after_extract', false)}
          onChange={(v) => save({ auto_cleanup_after_extract: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.auto_common_fixes')}
        hint={tS('automation_page.auto_common_fixes_hint')}
        data-testid="form-group-auto-process-common-fixes"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_common_fixes', false)}
          onChange={(v) => save({ auto_process_common_fixes: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.auto_hi_removal')}
        hint={tS('automation_page.auto_hi_removal_hint')}
        data-testid="form-group-auto-process-hi-removal"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_hi_removal', false)}
          onChange={(v) => save({ auto_process_hi_removal: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.auto_credit_removal')}
        hint={tS('automation_page.auto_credit_removal_hint')}
        data-testid="form-group-auto-process-credit-removal"
      >
        <Toggle
          checked={boolVal(config, 'auto_process_credit_removal', false)}
          onChange={(v) => save({ auto_process_credit_removal: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.nfo_export')}
        hint={tS('automation_page.nfo_export_hint')}
        data-testid="form-group-auto-nfo-export"
      >
        <Toggle
          checked={boolVal(config, 'auto_nfo_export', false)}
          onChange={(v) => save({ auto_nfo_export: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.jellyfin_translate')}
        hint={tS('automation_page.jellyfin_translate_hint')}
        data-testid="form-group-jellyfin-play-translate-enabled"
      >
        <Toggle
          checked={boolVal(config, 'jellyfin_play_translate_enabled', false)}
          onChange={(v) => save({ jellyfin_play_translate_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.streaming_enabled')}
        hint={tS('automation_page.streaming_enabled_hint')}
        data-testid="form-group-streaming-enabled"
      >
        <Toggle
          checked={boolVal(config, 'streaming_enabled', false)}
          onChange={(v) => save({ streaming_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.post_processing_enabled')}
        hint={tS('automation_page.post_processing_enabled_hint')}
        data-testid="form-group-post-processing-enabled"
      >
        <Toggle
          checked={boolVal(config, 'post_processing_enabled', false)}
          onChange={(v) => save({ post_processing_enabled: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={tS('automation_page.post_download_command')}
        hint={tS('automation_page.post_download_command_hint')}
        htmlFor="post-download-command"
        data-testid="form-group-post-download-command"
      >
        <textarea
          id="post-download-command"
          data-testid="input-post-download-command"
          style={{
            ...settingsInputStyle,
            width: '100%',
            minHeight: '60px',
            resize: 'vertical',
            fontFamily: 'monospace',
            fontSize: '12px',
          }}
          value={strVal(config, 'post_download_command', '')}
          onChange={(e) => save({ post_download_command: e.target.value })}
          disabled={updateConfig.isPending}
          placeholder="z.B. curl -s http://localhost:7878/api/refreshMonitor"
          spellCheck={false}
        />
      </FormGroup>
    </div>
  )
}

export function AutomationPostProcessingPage() {
  const { t } = useTranslation('common')
  const { t: tS } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={tS('post_processing_page.title')}
      subtitle={tS('post_processing_page.subtitle')}
    >
      <div data-testid="section-processing-pipeline">
        <SettingsSection
          title={t('settings.automation.pipeline.title', 'Processing Pipeline')}
          description={t(
            'settings.automation.pipeline.description',
            'Control post-download processing: translation, synchronisation, and cleanup.',
          )}
          icon={<Workflow size={16} style={{ color: 'var(--accent)' }} />}
          advanced={<ProcessingPipelineAdvancedContent />}
          advancedCount={2}
        >
          <ProcessingPipelineContent />
        </SettingsSection>
      </div>
    </SettingsDetailLayout>
  )
}
