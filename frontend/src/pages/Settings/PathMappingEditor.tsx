import { useState } from 'react'
import { Loader2, Plus, TestTube, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/components/shared/Toast'

export function PathMappingEditor({
  value,
  onChange,
}: {
  value: string
  onChange: (val: string) => void
}) {
  const { t } = useTranslation('settings')
  const [testPath, setTestPath] = useState('')
  const [testResult, setTestResult] = useState<{ mapped_path: string; exists: boolean } | null>(null)
  const [isTesting, setIsTesting] = useState(false)

  const handleTestPath = async () => {
    if (!testPath.trim()) return
    setIsTesting(true)
    try {
      const { default: api } = await import('@/api/client')
      const { data } = await api.post('/settings/path-mapping/test', { remote_path: testPath })
      setTestResult(data)
    } catch (error: unknown) {
      const msg = (error as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? t('path_mapping.test_failed')
      toast(msg, 'error')
      setTestResult(null)
    } finally {
      setIsTesting(false)
    }
  }

  const parseRows = (val: string): { remote: string; local: string }[] => {
    if (!val || !val.trim()) return []
    return val.split(';').filter(Boolean).map((pair) => {
      const eqIdx = pair.indexOf('=')
      if (eqIdx === -1) return { remote: pair, local: '' }
      return { remote: pair.slice(0, eqIdx), local: pair.slice(eqIdx + 1) }
    })
  }

  const rows = parseRows(value)

  const serialize = (r: { remote: string; local: string }[]) =>
    r.filter((x) => x.remote || x.local).map((x) => `${x.remote}=${x.local}`).join(';')

  const updateRow = (index: number, field: 'remote' | 'local', newVal: string) => {
    const updated = [...rows]
    updated[index] = { ...updated[index], [field]: newVal }
    onChange(serialize(updated))
  }

  const removeRow = (index: number) => {
    onChange(serialize(rows.filter((_, i) => i !== index)))
  }

  const addRow = () => {
    onChange(value ? value + ';=' : '=')
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {t('path_mapping.title')}
      </label>
      <div className="space-y-2">
        {rows.length > 0 && (
          // Column labels only from md up; below, the inputs stack and
          // carry the labels themselves (aria-label + placeholder).
          <div
            className="hidden md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] gap-2 text-xs font-medium"
            style={{ color: 'var(--text-muted)' }}
          >
            <span>{t('path_mapping.remote_path')}</span>
            <span>{t('path_mapping.local_path')}</span>
            <span />
          </div>
        )}
        {rows.map((row, i) => (
          // Below md remote and local stack in one column next to the remove
          // button; from md up the three sit in one row. minmax(0, 1fr) and
          // min-w-0 let the inputs shrink below their natural width.
          <div
            key={i}
            className="grid grid-cols-[minmax(0,1fr)_2rem] md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] gap-2 items-center"
          >
            <input
              type="text"
              value={row.remote}
              onChange={(e) => updateRow(i, 'remote', e.target.value)}
              placeholder="/data/media"
              aria-label={t('path_mapping.remote_path')}
              className="col-start-1 row-start-1 w-full min-w-0 px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <input
              type="text"
              value={row.local}
              onChange={(e) => updateRow(i, 'local', e.target.value)}
              placeholder={t('path_mapping.example_windows')}
              aria-label={t('path_mapping.local_path')}
              className="col-start-1 row-start-2 md:col-start-2 md:row-start-1 w-full min-w-0 px-3 py-2 rounded-md text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
            />
            <button
              onClick={() => removeRow(i)}
              className="col-start-2 row-start-1 row-span-2 md:col-start-3 md:row-span-1 justify-self-center p-1.5 rounded transition-all duration-150"
              style={{ color: 'var(--text-muted)' }}
              title={t('path_mapping.remove_mapping')}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <button
          onClick={addRow}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150"
          style={{
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            backgroundColor: 'var(--bg-primary)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--accent-dim)'
            e.currentTarget.style.color = 'var(--accent)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text-secondary)'
          }}
        >
          <Plus size={12} />
          {t('path_mapping.add_mapping')}
        </button>
      </div>
      {/* Test Path Mapping */}
      <div className="pt-3 space-y-2" style={{ borderTop: '1px solid var(--border)' }}>
        <label className="block text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {t('path_mapping.test_title')}
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={testPath}
            onChange={(e) => setTestPath(e.target.value)}
            placeholder="/data/media/anime/Series.mkv"
            className="flex-1 min-w-0 px-3 py-2 rounded-md text-sm focus:outline-none"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleTestPath()
            }}
          />
          <button
            onClick={handleTestPath}
            disabled={isTesting || !testPath.trim()}
            className="flex shrink-0 items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-all duration-150"
            style={{
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-primary)',
            }}
            onMouseEnter={(e) => {
              if (!e.currentTarget.disabled) {
                e.currentTarget.style.borderColor = 'var(--accent-dim)'
                e.currentTarget.style.color = 'var(--accent)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color = 'var(--text-secondary)'
            }}
          >
            {isTesting ? <Loader2 size={14} className="animate-spin" /> : <TestTube size={14} />}
            {t('path_mapping.test')}
          </button>
        </div>
        {testResult && (
          <div className="text-xs space-y-1 break-all" style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>{t('path_mapping.mapped_to')}</span>{' '}
              <span style={{ color: 'var(--accent)' }}>{testResult.mapped_path}</span>
            </div>
            <div>
              <span style={{ color: testResult.exists ? 'var(--success)' : 'var(--error)' }}>
                {testResult.exists ? t('path_mapping.file_exists') : t('path_mapping.file_not_found')}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
