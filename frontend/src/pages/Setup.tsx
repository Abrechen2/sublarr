import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Unlock, Eye, EyeOff } from 'lucide-react'
import { setupAuth } from '@/api/client'
import { toast } from '@/components/shared/Toast'

export function SetupPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')

  const { mutate: doSetup, isPending } = useMutation({
    mutationFn: setupAuth,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-status'] })
      navigate('/')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Setup failed'
      // "Already configured" means auth is already set up (e.g. AUTH_ENABLED=false in env) — just navigate
      if (msg.includes('Already configured')) {
        queryClient.invalidateQueries({ queryKey: ['auth-status'] })
        navigate('/')
        return
      }
      toast(msg, 'error')
    },
  })

  function handleSetPassword(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (password.length < 4) { setError('Password must be at least 4 characters.'); return }
    if (password !== confirm) { setError('Passwords do not match.'); return }
    doSetup({ action: 'set_password', password })
  }

  function handleDisable() { doSetup({ action: 'disable' }) }

  const inputStyle = {
    backgroundColor: 'var(--bg-input)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    outline: 'none',
  }

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ backgroundColor: 'var(--bg-base)' }}>
      <div className="w-full max-w-md rounded-xl p-8 shadow-xl" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full" style={{ backgroundColor: 'var(--accent-muted)' }}>
            <Lock size={24} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Welcome to Sublarr</h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--text-muted)' }}>
            Set a password to protect the UI, or leave it open.
          </p>
        </div>

        <form onSubmit={handleSetPassword} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter a password…"
                className="w-full rounded-lg px-3 py-2 pr-10 text-sm"
                style={inputStyle}
                autoFocus
              />
              <button type="button" onClick={() => setShowPassword((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}
                aria-label={showPassword ? 'Hide password' : 'Show password'}>
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>Confirm Password</label>
            <input
              type={showPassword ? 'text' : 'password'}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat password…"
              className="w-full rounded-lg px-3 py-2 text-sm"
              style={inputStyle}
            />
          </div>
          {error && <p className="text-sm" style={{ color: 'var(--color-error)' }}>{error}</p>}
          <button type="submit" disabled={isPending || !password}
            className="w-full rounded-lg py-2 text-sm font-semibold transition-opacity disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)', color: '#fff' }}>
            {isPending ? 'Setting up…' : 'Set Password & Continue'}
          </button>
        </form>

        <div className="mt-4">
          <div className="relative my-4 flex items-center">
            <div className="flex-1" style={{ borderTop: '1px solid var(--border)' }} />
            <span className="mx-3 text-xs" style={{ color: 'var(--text-muted)' }}>or</span>
            <div className="flex-1" style={{ borderTop: '1px solid var(--border)' }} />
          </div>
          <button type="button" onClick={handleDisable} disabled={isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg py-2 text-sm transition-opacity hover:opacity-80 disabled:opacity-50"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
            <Unlock size={14} />
            Continue without password (open access)
          </button>
        </div>
      </div>
    </div>
  )
}
