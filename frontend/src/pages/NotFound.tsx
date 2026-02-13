import { useNavigate } from 'react-router-dom'
import { Home } from 'lucide-react'

export function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div
        className="max-w-sm w-full rounded-lg p-8 text-center"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <div
          className="text-5xl font-bold mb-2"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}
        >
          404
        </div>
        <h1 className="text-lg font-semibold mb-2">Page Not Found</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
          The page you're looking for doesn't exist or has been moved.
        </p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Home size={14} />
          Go to Dashboard
        </button>
      </div>
    </div>
  )
}
