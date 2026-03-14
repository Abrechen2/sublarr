import { useQuery } from '@tanstack/react-query'
import { Navigate, useLocation } from 'react-router-dom'
import { getAuthStatus } from '@/api/client'

interface AuthGuardProps {
  children: React.ReactNode
}

export function AuthGuard({ children }: AuthGuardProps) {
  const location = useLocation()
  const { data: auth, isLoading } = useQuery({
    queryKey: ['auth-status'],
    queryFn: getAuthStatus,
    staleTime: 30_000,
    retry: false,
  })

  if (isLoading) return null

  if (auth && !auth.configured) {
    return <Navigate to="/setup" replace />
  }
  if (auth?.configured && auth.enabled && !auth.authenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <>{children}</>
}
