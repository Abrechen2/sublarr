import { useNavigate } from 'react-router-dom'
import { Home, ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function NotFoundPage() {
  const navigate = useNavigate()
  const { t } = useTranslation('common')

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
        <h1 className="text-lg font-semibold mb-2">{t('not_found.title')}</h1>
        <p className="text-sm mb-6" style={{ color: 'var(--text-secondary)' }}>
          {t('not_found.message')}
        </p>
        <div className="flex justify-center flex-wrap gap-4">
          <button
            onClick={() => navigate(-1)}
            data-testid="not-found-back"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          >
            <ArrowLeft size={14} />
            {t('not_found.go_back')}
          </button>
          <button
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Home size={14} />
            {t('not_found.go_dashboard')}
          </button>
        </div>
      </div>
    </div>
  )
}
