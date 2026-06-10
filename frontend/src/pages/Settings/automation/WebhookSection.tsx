/**
 * Webhook + Scheduled-Tasks sections for AutomationSettings.
 * Extracted from AutomationSettings.tsx during the file-size split.
 */
import { useTranslation } from 'react-i18next'
import { FormGroup } from '@/components/settings/FormGroup'
import { Toggle } from '@/components/shared/Toggle'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { strVal, boolVal } from '@/lib/configUtils'
import { inputStyle, SectionSkeleton } from './shared'

export function WebhookContent() {
  const { t } = useTranslation('settings')
  const { data: config, isLoading } = useConfig()
  const updateConfig = useUpdateConfig()

  const save = (patch: Record<string, unknown>) => updateConfig.mutate(patch)

  if (isLoading) return <SectionSkeleton />

  return (
    <div data-testid="webhook-content">
      <FormGroup
        label={t('automation_page.webhook_delay')}
        hint={t('automation_page.webhook_delay_hint')}
        htmlFor="webhook-delay-minutes"
        data-testid="form-group-webhook-delay-minutes"
      >
        <input
          id="webhook-delay-minutes"
          type="number"
          data-testid="input-webhook-delay-minutes"
          style={{ ...inputStyle, maxWidth: '120px' }}
          value={strVal(config, 'webhook_delay_minutes', '5')}
          onChange={(e) => save({ webhook_delay_minutes: Number(e.target.value) })}
          disabled={updateConfig.isPending}
          min={0}
          placeholder="5"
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_scan')}
        hint={t('automation_page.webhook_auto_scan_hint')}
        htmlFor="webhook-auto-scan"
        data-testid="form-group-webhook-auto-scan"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_scan', false)}
          onChange={(v) => save({ webhook_auto_scan: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_search')}
        hint={t('automation_page.webhook_auto_search_hint')}
        htmlFor="webhook-auto-search"
        data-testid="form-group-webhook-auto-search"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_search', true)}
          onChange={(v) => save({ webhook_auto_search: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>

      <FormGroup
        label={t('automation_page.webhook_auto_translate')}
        hint={t('automation_page.webhook_auto_translate_hint')}
        htmlFor="webhook-auto-translate"
        data-testid="form-group-webhook-auto-translate"
      >
        <Toggle
          checked={boolVal(config, 'webhook_auto_translate', false)}
          onChange={(v) => save({ webhook_auto_translate: v })}
          disabled={updateConfig.isPending}
        />
      </FormGroup>
    </div>
  )
}

// ─── Scheduled Tasks Section (advanced placeholder) ───────────────────────────

export function ScheduledTasksContent() {
  const { t } = useTranslation('settings')

  return (
    <div data-testid="scheduled-tasks-content">
      <p className="text-[12px] text-[var(--text-muted)] py-3">
        {t(
          'settings.automation.scheduledTasks.hint',
          'Scheduled task details and run history can be viewed on the Tasks page.',
        )}
      </p>
    </div>
  )
}
