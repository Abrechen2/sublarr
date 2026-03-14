import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Eye, EyeOff } from 'lucide-react'
import { login } from '@/api/client'
import { toast } from '@/components/shared/Toast'

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const from = (location.state as { from?: string })?.from ?? '/'

  const { mutate: doLogin, isPending, isError } = useMutation({
    mutationFn: () => login(password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth-status'] })
      navigate(from, { replace: true })
    },
    onError: () => toast('Invalid password', 'error'),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (password) doLogin()
  }

  return (
    <div className="flex min-h-screen items-center justify-center" style={{ backgroundColor: 'var(--bg-base)' }}>
      <div className="w-full max-w-sm rounded-xl p-8 shadow-xl" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full" style={{ backgroundColor: 'var(--accent-muted)' }}>
            <Lock size={24} style={{ color: 'var(--accent)' }} />
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>Sublarr</h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>Enter your password to continue</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full rounded-lg px-3 py-2 pr-10 text-sm"
              style={{
                backgroundColor: 'var(--bg-input)',
                border: `1px solid ${isError ? 'var(--color-error)' : 'var(--border)'}`,
                color: 'var(--text-primary)',
                outline: 'none',
              }}
              autoFocus
            />
            <button type="button" onClick={() => setShowPassword((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }}
              aria-label={showPassword ? 'Hide password' : 'Show password'}>
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          <button type="submit" disabled={isPending || !password}
            className="w-full rounded-lg py-2 text-sm font-semibold transition-opacity disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)', color: '#fff' }}>
            {isPending ? 'Logging in…' : 'Log In'}
          </button>
        </form>
      </div>
    </div>
  )
}
