import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Shield, Eye, EyeOff } from 'lucide-react'
import { getAuthStatus, toggleAuth, changePassword } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { SettingsCard } from '@/components/shared/SettingsCard'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'
import { FormGroup } from '@/components/settings/FormGroup'
import { useConfig, useUpdateConfig } from '@/hooks/useApi'
import { numVal, strVal } from '@/lib/configUtils'

export function SecurityTab() {
  const { t } = useTranslation('settings')
  const queryClient = useQueryClient()
  const { data: auth } = useQuery({ queryKey: ['auth-status'], queryFn: getAuthStatus })
  const { data: config } = useConfig()
  const { mutate: saveConfig } = useUpdateConfig()
  const save = (patch: Record<string, unknown>) => saveConfig(patch)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [pwError, setPwError] = useState('')

  const { mutate: doToggle, isPending: toggling } = useMutation({
    mutationFn: (enabled: boolean) => toggleAuth(enabled),
    onSuccess: (_, enabled) => {
      queryClient.invalidateQueries({ queryKey: ['auth-status'] })
      toast(enabled ? t('security_tab.auth_enabled') : t('security_tab.auth_disabled'), 'success')
    },
    onError: () => toast(t('security_tab.auth_update_failed'), 'error'),
  })

  const { mutate: doChangePw, isPending: changingPw } = useMutation({
    mutationFn: () => changePassword(currentPw, newPw),
    onSuccess: () => {
      setCurrentPw(''); setNewPw(''); setConfirmPw(''); setPwError('')
      toast(t('security_tab.password_changed'), 'success')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? t('security_tab.failed')
      toast(msg, 'error')
    },
  })

  function handleChangePw(e: React.FormEvent) {
    e.preventDefault()
    setPwError('')
    if (newPw.length < 8) { setPwError(t('security_tab.pw_too_short')); return }
    if (newPw !== confirmPw) { setPwError(t('security_tab.pw_mismatch')); return }
    doChangePw()
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-input)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', borderRadius: '0.5rem',
    padding: '0.375rem 0.75rem', fontSize: '0.875rem', width: '100%', outline: 'none',
  }

  const numInputStyle = {
    backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', borderRadius: '0.375rem',
    padding: '0.375rem 0.75rem', fontSize: '0.8125rem', outline: 'none', width: '120px',
  }

  const wideInputStyle = {
    backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', borderRadius: '0.375rem',
    padding: '0.375rem 0.75rem', fontSize: '0.8125rem', outline: 'none', width: '300px',
  }

  return (
    <div className="space-y-6">
      <SettingsCard title={t('security.ui_auth_title')} icon={Shield}>
        <SettingRow label={t('security.require_login')}
          description={t('security.require_login_desc')}>
          <Toggle checked={auth?.enabled ?? false} onChange={(v) => doToggle(v)} disabled={toggling} />
        </SettingRow>
      </SettingsCard>

      {auth?.enabled && (
        <SettingsCard title={t('security.change_password_title')} icon={Shield}>
          <form onSubmit={handleChangePw} className="space-y-3 pt-1">
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('security.current_password')}</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)} style={{ ...inputStyle, paddingRight: '2.5rem' }} />
                <button type="button" onClick={() => setShowPw((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}
                  aria-label={showPw ? t('security_tab.hide') : t('security_tab.show')}>
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('security.new_password')}</label>
              <input type={showPw ? 'text' : 'password'} value={newPw} onChange={(e) => setNewPw(e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{t('security.confirm_new_password')}</label>
              <input type={showPw ? 'text' : 'password'} value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} style={inputStyle} />
            </div>
            {pwError && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{pwError}</p>}
            <button type="submit" disabled={changingPw || !currentPw || !newPw || !confirmPw}
              className="rounded-lg px-4 py-1.5 text-sm font-semibold transition-opacity disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)', color: '#fff' }}>
              {changingPw ? t('security_tab.saving') : t('security_tab.change_password')}
            </button>
          </form>
        </SettingsCard>
      )}

      {/* Rate Limiting & Session (Step 46) */}
      <div data-testid="section-extended-security">
        <SettingsCard title={t('security_tab.rate_limiting_session')} icon={Shield}>
          <div className="space-y-4 pt-1">
            <FormGroup
              label={t('security_tab.session_timeout')}
              hint={t('security_tab.session_timeout_hint')}
              data-testid="form-group-session-timeout-minutes"
            >
              <input
                data-testid="input-session-timeout-minutes"
                type="number"
                min={0}
                value={numVal(config, 'session_timeout_minutes', 0)}
                onChange={(e) => save({ session_timeout_minutes: Number(e.target.value) })}
                style={numInputStyle}
              />
            </FormGroup>
            <FormGroup
              label={t('security.max_login_attempts')}
              hint={t('security.max_login_attempts_hint')}
              data-testid="form-group-max-login-attempts"
            >
              <input
                data-testid="input-max-login-attempts"
                type="number"
                min={1}
                max={100}
                value={numVal(config, 'max_login_attempts', 20)}
                onChange={(e) => save({ max_login_attempts: Number(e.target.value) })}
                style={numInputStyle}
              />
            </FormGroup>
            <FormGroup
              label={t('security.lockout_duration')}
              hint={t('security.lockout_duration_hint')}
              data-testid="form-group-lockout-duration-minutes"
            >
              <input
                data-testid="input-lockout-duration-minutes"
                type="number"
                min={1}
                max={1440}
                value={numVal(config, 'lockout_duration_minutes', 60)}
                onChange={(e) => save({ lockout_duration_minutes: Number(e.target.value) })}
                style={numInputStyle}
              />
            </FormGroup>
            <FormGroup
              label={t('security.allowed_ip_ranges')}
              hint={t('security_tab.allowed_ip_ranges_hint')}
              data-testid="form-group-allowed-ip-ranges"
            >
              <input
                data-testid="input-allowed-ip-ranges"
                type="text"
                placeholder="192.168.1.0/24, 10.0.0.0/8"
                value={strVal(config, 'allowed_ip_ranges', '')}
                onChange={(e) => save({ allowed_ip_ranges: e.target.value })}
                style={wideInputStyle}
              />
            </FormGroup>
          </div>
        </SettingsCard>
      </div>
    </div>
  )
}
