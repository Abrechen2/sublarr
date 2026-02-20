import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useApiKeys, useUpdateApiKey, useTestApiKey,
  useExportApiKeys, useImportApiKeys,
  useBazarrMigration, useConfirmBazarrImport,
} from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import {
  Loader2, Shield, ShieldCheck, ShieldAlert, TestTube,
  FileDown, Upload, Eye, EyeOff, Check, X, KeyRound,
} from 'lucide-react'
import type { ApiKeyService, BazarrMigrationPreview } from '@/lib/types'

// ─── Service Key Card ────────────────────────────────────────────────────────

function ServiceKeyCard({
  service,
  onUpdate,
  onTest,
}: {
  service: ApiKeyService
  onUpdate: (service: string, keyName: string, value: string) => void
  onTest: (service: string) => void
}) {
  const { t } = useTranslation('settings')
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})

  const handleStartEdit = (keyName: string) => {
    setEditingKey(keyName)
    setEditValue('')
  }

  const handleSave = (keyName: string) => {
    if (editValue.trim()) {
      onUpdate(service.service, keyName, editValue.trim())
    }
    setEditingKey(null)
    setEditValue('')
  }

  const handleCancel = () => {
    setEditingKey(null)
    setEditValue('')
  }

  const toggleShow = (keyName: string) => {
    setShowValues((prev) => ({ ...prev, [keyName]: !prev[keyName] }))
  }

  const allConfigured = service.keys.every((k) => k.status === 'configured')
  const anyMissing = service.keys.some((k) => k.status === 'missing')

  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {allConfigured ? (
            <ShieldCheck size={16} style={{ color: 'var(--success)' }} />
          ) : anyMissing ? (
            <ShieldAlert size={16} style={{ color: 'var(--error)' }} />
          ) : (
            <Shield size={16} style={{ color: 'var(--text-muted)' }} />
          )}
          <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {service.service}
          </h3>
        </div>
        {service.testable && (
          <button
            onClick={() => onTest(service.service)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all duration-150"
            style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--accent-bg)' }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
          >
            <TestTube size={12} />
            {t('actions.test')}
          </button>
        )}
      </div>

      <div className="space-y-2">
        {service.keys.map((key) => (
          <div
            key={key.name}
            className="flex items-center gap-3 px-3 py-2 rounded-md"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <KeyRound size={12} style={{ color: 'var(--text-muted)' }} />
                <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                  {key.name}
                </span>
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                  style={{
                    backgroundColor: key.status === 'configured' ? 'var(--success-bg, rgba(34,197,94,0.1))' : 'var(--error-bg, rgba(239,68,68,0.1))',
                    color: key.status === 'configured' ? 'var(--success)' : 'var(--error)',
                  }}
                >
                  {key.status}
                </span>
              </div>
              {editingKey === key.name ? (
                <div className="flex items-center gap-2 mt-1.5">
                  <input
                    type="password"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    placeholder="Enter new value..."
                    className="flex-1 px-2 py-1 rounded text-xs focus:outline-none"
                    style={{
                      backgroundColor: 'var(--bg-surface)',
                      border: '1px solid var(--accent-dim)',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-mono)',
                    }}
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSave(key.name)
                      if (e.key === 'Escape') handleCancel()
                    }}
                  />
                  <button
                    onClick={() => handleSave(key.name)}
                    className="p-1 rounded"
                    style={{ color: 'var(--success)' }}
                    title="Save"
                  >
                    <Check size={14} />
                  </button>
                  <button
                    onClick={handleCancel}
                    className="p-1 rounded"
                    style={{ color: 'var(--text-muted)' }}
                    title="Cancel"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2 mt-1">
                  <code
                    className="text-xs"
                    style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
                  >
                    {showValues[key.name] && key.masked_value !== '(not set)'
                      ? key.masked_value
                      : key.status === 'configured'
                        ? '\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022'
                        : '(not set)'}
                  </code>
                  {key.status === 'configured' && (
                    <button
                      onClick={() => toggleShow(key.name)}
                      className="p-0.5 rounded"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {showValues[key.name] ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  )}
                  <button
                    onClick={() => handleStartEdit(key.name)}
                    className="text-[10px] px-1.5 py-0.5 rounded font-medium transition-all duration-150"
                    style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'var(--accent-bg)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent' }}
                  >
                    {key.status === 'configured' ? 'Rotate' : 'Set'}
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Bazarr Migration Modal ──────────────────────────────────────────────────

function BazarrPreviewModal({
  preview,
  onConfirm,
  onCancel,
  isPending,
}: {
  preview: BazarrMigrationPreview
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div
      className="rounded-lg p-4 space-y-3"
      style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
    >
      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
        Bazarr Migration Preview
      </div>

      {preview.warnings.length > 0 && (
        <div className="space-y-1">
          {preview.warnings.map((w, i) => (
            <div key={i} className="text-xs px-2 py-1 rounded" style={{ backgroundColor: 'var(--warning-bg, rgba(234,179,8,0.1))', color: 'var(--warning)' }}>
              {w}
            </div>
          ))}
        </div>
      )}

      <div
        className="max-h-48 overflow-auto rounded px-3 py-2 text-xs space-y-1"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          color: 'var(--text-secondary)',
        }}
      >
        {preview.config_entries.map((entry) => (
          <div key={entry.key} className="flex items-center gap-2 py-0.5">
            <span style={{ color: 'var(--accent)' }}>{entry.key}</span>
            <span style={{ color: 'var(--text-muted)' }}>=</span>
            <span>{entry.value}</span>
            {entry.current_value && (
              <span className="text-[10px]" style={{ color: 'var(--warning)' }}>
                (current: {entry.current_value})
              </span>
            )}
          </div>
        ))}
      </div>

      <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
        {preview.config_entries.length} config entries
        {preview.blacklist_count > 0 && `, ${preview.blacklist_count} blacklist entries`}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onConfirm}
          disabled={isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          {isPending ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          Confirm Import
        </button>
        <button
          onClick={onCancel}
          className="flex items-center gap-1 px-3 py-1.5 rounded text-xs"
          style={{ color: 'var(--text-muted)' }}
        >
          <X size={12} />
          Cancel
        </button>
      </div>
    </div>
  )
}

// ─── Main ApiKeysTab Component ───────────────────────────────────────────────

export function ApiKeysTab() {
  const { t } = useTranslation('settings')
  const { data, isLoading } = useApiKeys()
  const updateKey = useUpdateApiKey()
  const testKey = useTestApiKey()
  const exportKeys = useExportApiKeys()
  const importKeys = useImportApiKeys()
  const bazarrMigrate = useBazarrMigration()
  const confirmBazarr = useConfirmBazarrImport()

  const importFileRef = useRef<HTMLInputElement>(null)
  const bazarrFileRef = useRef<HTMLInputElement>(null)
  const [bazarrPreview, setBazarrPreview] = useState<BazarrMigrationPreview | null>(null)

  const handleUpdate = (service: string, keyName: string, value: string) => {
    updateKey.mutate({ service, keyName, value }, {
      onSuccess: () => toast(t('apiKeys.keyUpdated', 'Key updated successfully')),
      onError: () => toast(t('apiKeys.keyUpdateFailed', 'Failed to update key'), 'error'),
    })
  }

  const handleTest = (service: string) => {
    testKey.mutate(service, {
      onSuccess: (result) => {
        if (result.success) {
          toast(`${service}: ${result.message}`)
        } else {
          toast(`${service}: ${result.message}`, 'error')
        }
      },
      onError: () => toast(`${service}: Connection failed`, 'error'),
    })
  }

  const handleExport = () => {
    exportKeys.mutate(undefined, {
      onSuccess: (blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `sublarr-api-keys-${new Date().toISOString().slice(0, 10)}.zip`
        a.click()
        URL.revokeObjectURL(url)
        toast(t('apiKeys.exportSuccess', 'API keys exported'))
      },
      onError: () => toast(t('apiKeys.exportFailed', 'Export failed'), 'error'),
    })
  }

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    importKeys.mutate(file, {
      onSuccess: (result) => {
        toast(`Imported ${result.imported} keys` + (result.skipped > 0 ? ` (${result.skipped} skipped)` : ''))
      },
      onError: () => toast(t('apiKeys.importFailed', 'Import failed'), 'error'),
    })
    e.target.value = ''
  }

  const handleBazarrFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    bazarrMigrate.mutate(file, {
      onSuccess: (preview) => {
        setBazarrPreview(preview)
      },
      onError: () => toast('Failed to parse Bazarr config', 'error'),
    })
    e.target.value = ''
  }

  const handleBazarrConfirm = () => {
    if (!bazarrPreview) return
    confirmBazarr.mutate(bazarrPreview, {
      onSuccess: (result) => {
        setBazarrPreview(null)
        toast(`Bazarr import complete: ${result.imported} entries imported`)
      },
      onError: () => toast('Bazarr import failed', 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <Loader2 size={24} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  const services = data?.services ?? []

  return (
    <div className="space-y-5">
      {/* Header */}
      <div
        className="rounded-lg p-4"
        style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
      >
        <h2 className="text-sm font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
          {t('apiKeys.title', 'API Key Management')}
        </h2>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          {t('apiKeys.description', 'Manage all API keys in one place. Test connections, rotate keys, and import/export configurations.')}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleExport}
            disabled={exportKeys.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent-dim)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
          >
            {exportKeys.isPending ? <Loader2 size={12} className="animate-spin" /> : <FileDown size={12} />}
            {t('apiKeys.export', 'Export Keys')}
          </button>

          <button
            onClick={() => importFileRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent-dim)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
          >
            <Upload size={12} />
            {t('apiKeys.import', 'Import Keys')}
          </button>
          <input ref={importFileRef} type="file" accept=".zip,.csv" onChange={handleImportFile} className="hidden" />

          <div style={{ borderLeft: '1px solid var(--border)', height: '20px' }} />

          <button
            onClick={() => bazarrFileRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all duration-150"
            style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent-dim)'; e.currentTarget.style.color = 'var(--accent)' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
          >
            <Upload size={12} />
            {t('apiKeys.bazarrImport', 'Bazarr Migration')}
          </button>
          <input ref={bazarrFileRef} type="file" accept=".yaml,.yml,.ini,.db" onChange={handleBazarrFile} className="hidden" />
        </div>
      </div>

      {/* Bazarr Preview */}
      {bazarrPreview && (
        <BazarrPreviewModal
          preview={bazarrPreview}
          onConfirm={handleBazarrConfirm}
          onCancel={() => setBazarrPreview(null)}
          isPending={confirmBazarr.isPending}
        />
      )}

      {/* Service Cards */}
      <div className="grid gap-3">
        {services.map((service: ApiKeyService) => (
          <ServiceKeyCard
            key={service.service}
            service={service}
            onUpdate={handleUpdate}
            onTest={handleTest}
          />
        ))}
      </div>

      {services.length === 0 && (
        <div
          className="rounded-lg p-8 text-center"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <Shield size={32} className="mx-auto mb-2" style={{ color: 'var(--text-muted)' }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {t('apiKeys.noServices', 'No API key services found.')}
          </p>
        </div>
      )}
    </div>
  )
}
