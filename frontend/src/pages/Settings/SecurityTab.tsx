import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Shield, Eye, EyeOff } from 'lucide-react'
import { getAuthStatus, toggleAuth, changePassword } from '@/api/client'
import { toast } from '@/components/shared/Toast'
import { SettingsCard } from '@/components/shared/SettingsCard'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'

export function SecurityTab() {
  const queryClient = useQueryClient()
  const { data: auth } = useQuery({ queryKey: ['auth-status'], queryFn: getAuthStatus })
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [pwError, setPwError] = useState('')

  const { mutate: doToggle, isPending: toggling } = useMutation({
    mutationFn: (enabled: boolean) => toggleAuth(enabled),
    onSuccess: (_, enabled) => {
      queryClient.invalidateQueries({ queryKey: ['auth-status'] })
      toast(`UI authentication ${enabled ? 'enabled' : 'disabled'}`, 'success')
    },
    onError: () => toast('Failed to update authentication setting', 'error'),
  })

  const { mutate: doChangePw, isPending: changingPw } = useMutation({
    mutationFn: () => changePassword(currentPw, newPw),
    onSuccess: () => {
      setCurrentPw(''); setNewPw(''); setConfirmPw(''); setPwError('')
      toast('Password changed', 'success')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Failed'
      toast(msg, 'error')
    },
  })

  function handleChangePw(e: React.FormEvent) {
    e.preventDefault()
    setPwError('')
    if (newPw.length < 4) { setPwError('New password must be at least 4 characters.'); return }
    if (newPw !== confirmPw) { setPwError('Passwords do not match.'); return }
    doChangePw()
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-input)', border: '1px solid var(--border)',
    color: 'var(--text-primary)', borderRadius: '0.5rem',
    padding: '0.375rem 0.75rem', fontSize: '0.875rem', width: '100%', outline: 'none',
  }

  return (
    <div className="space-y-6">
      <SettingsCard title="UI Authentication" icon={Shield}>
        <SettingRow label="Require login"
          description="Protect the web UI with a password. API key authentication is unaffected.">
          <Toggle checked={auth?.enabled ?? false} onChange={(v) => doToggle(v)} disabled={toggling} />
        </SettingRow>
      </SettingsCard>

      {auth?.enabled && (
        <SettingsCard title="Change Password" icon={Shield}>
          <form onSubmit={handleChangePw} className="space-y-3 pt-1">
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Current Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)} style={{ ...inputStyle, paddingRight: '2.5rem' }} />
                <button type="button" onClick={() => setShowPw((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}
                  aria-label={showPw ? 'Hide' : 'Show'}>
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>New Password</label>
              <input type={showPw ? 'text' : 'password'} value={newPw} onChange={(e) => setNewPw(e.target.value)} style={inputStyle} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>Confirm New Password</label>
              <input type={showPw ? 'text' : 'password'} value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} style={inputStyle} />
            </div>
            {pwError && <p className="text-xs" style={{ color: 'var(--color-error)' }}>{pwError}</p>}
            <button type="submit" disabled={changingPw || !currentPw || !newPw || !confirmPw}
              className="rounded-lg px-4 py-1.5 text-sm font-semibold transition-opacity disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)', color: '#fff' }}>
              {changingPw ? 'Saving…' : 'Change Password'}
            </button>
          </form>
        </SettingsCard>
      )}
    </div>
  )
}
