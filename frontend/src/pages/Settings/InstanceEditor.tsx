import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface InstanceEntry {
  name: string
  url: string
  api_key: string
  path_mapping?: string
}

export function InstanceEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (val: string) => void
}) {
  const { t } = useTranslation('settings')
  const [instances, setInstances] = useState<InstanceEntry[]>(() => {
    try {
      const parsed = JSON.parse(value || '[]')
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })

  const sync = (updated: InstanceEntry[]) => {
    setInstances(updated)
    onChange(updated.length > 0 ? JSON.stringify(updated) : '')
  }

  const addInstance = () => {
    sync([...instances, { name: '', url: '', api_key: '', path_mapping: '' }])
  }

  const removeInstance = (idx: number) => {
    sync(instances.filter((_, i) => i !== idx))
  }

  const updateField = (idx: number, field: keyof InstanceEntry, val: string) => {
    const updated = [...instances]
    updated[idx] = { ...updated[idx], [field]: val }
    sync(updated)
  }

  const inputStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontSize: '13px',
  }

  return (
    <div className="pt-3 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('instance_editor.instances_label', { label })}
        </h3>
        <button
          onClick={addInstance}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
        >
          <Plus size={12} />
          {t('instance_editor.add_instance')}
        </button>
      </div>
      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {t('instance_editor.configure_hint', { label })}
      </p>
      {instances.map((inst, idx) => (
        <div
          key={idx}
          className="rounded-lg p-3 space-y-2"
          style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
              {t('instance_editor.instance_n', { n: idx + 1 })}
            </span>
            <button
              onClick={() => removeInstance(idx)}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              <Trash2 size={12} />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input
              type="text"
              placeholder={t('instance_editor.name_placeholder')}
              value={inst.name}
              onChange={(e) => updateField(idx, 'name', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder={t('instance_editor.url_placeholder')}
              value={inst.url}
              onChange={(e) => updateField(idx, 'url', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="password"
              placeholder="API Key"
              value={inst.api_key}
              onChange={(e) => updateField(idx, 'api_key', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
            <input
              type="text"
              placeholder={t('instance_editor.path_mapping_placeholder')}
              value={inst.path_mapping || ''}
              onChange={(e) => updateField(idx, 'path_mapping', e.target.value)}
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={inputStyle}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
