import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Plus, Edit2, Trash2, Check, X } from 'lucide-react'
import { toast } from '@/components/shared/Toast'
import {
  usePromptPresets, useCreatePromptPreset, useUpdatePromptPreset, useDeletePromptPreset,
} from '@/hooks/useApi'

// ─── Prompt Presets Tab ────────────────────────────────────────────────────────

export function PromptPresetsTab() {
  const { t } = useTranslation('settings')
  const { data, isLoading } = usePromptPresets()
  const createPreset = useCreatePromptPreset()
  const updatePreset = useUpdatePromptPreset()
  const deletePreset = useDeletePromptPreset()
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formData, setFormData] = useState({ name: '', prompt_template: '', is_default: false })

  const presets = data?.presets || []

  const resetForm = () => {
    setShowAdd(false)
    setEditingId(null)
    setFormData({ name: '', prompt_template: '', is_default: false })
  }

  const startEdit = (preset: { id: number; name: string; prompt_template: string; is_default: number }) => {
    setEditingId(preset.id)
    setFormData({
      name: preset.name,
      prompt_template: preset.prompt_template,
      is_default: preset.is_default === 1,
    })
    setShowAdd(false)
  }

  const handleSave = () => {
    if (!formData.name.trim() || !formData.prompt_template.trim()) {
      toast(t('prompt_presets_tab.toast_fields_required'), 'error')
      return
    }

    if (editingId) {
      updatePreset.mutate(
        { presetId: editingId, ...formData },
        {
          onSuccess: () => {
            toast(t('prompt_presets_tab.toast_updated'))
            resetForm()
          },
          onError: () => toast(t('prompt_presets_tab.toast_update_failed'), 'error'),
        }
      )
    } else {
      createPreset.mutate(formData, {
        onSuccess: () => {
          toast(t('prompt_presets_tab.toast_created'))
          resetForm()
        },
        onError: () => toast(t('prompt_presets_tab.toast_create_failed'), 'error'),
      })
    }
  }

  const handleDelete = (id: number) => {
    if (!confirm(t('prompt_presets_tab.confirm_delete'))) return
    deletePreset.mutate(id, {
      onSuccess: () => toast(t('prompt_presets_tab.toast_deleted')),
      onError: () => toast(t('prompt_presets_tab.toast_delete_failed'), 'error'),
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent)' }} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg p-4 mb-4 text-sm" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
        <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>{t('prompt_presets_tab.available_variables')}</p>
        <p className="font-mono text-xs" style={{ color: 'var(--accent)' }}>{'{title}'} {'{context}'} {'{source_lang}'} {'{target_lang}'} {'{line_count}'}</p>
        <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>{t('prompt_presets_tab.variables_note')}</p>
      </div>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('prompt_presets_tab.title')}
        </h2>
        <button
          onClick={() => {
            resetForm()
            setShowAdd(true)
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Plus size={12} />
          {t('prompt_presets_tab.add_preset')}
        </button>
      </div>

      {showAdd && (
        <div
          className="rounded-lg p-4 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--accent-dim)' }}
        >
          <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {editingId ? t('prompt_presets_tab.edit_preset_form') : t('prompt_presets_tab.new_preset_form')}
          </div>
          <div className="space-y-2">
            <input
              type="text"
              placeholder={t('prompt_presets_tab.preset_name')}
              value={formData.name}
              onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-3 py-2 rounded-md text-sm"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <textarea
              placeholder={t('prompt_presets_tab.prompt_template_placeholder')}
              value={formData.prompt_template}
              onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
              rows={8}
              className="w-full px-3 py-2 rounded-md text-sm font-mono"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
              }}
            />
            <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <input
                type="checkbox"
                checked={formData.is_default}
                onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
              />
              {t('prompt_presets_tab.set_as_default')}
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={createPreset.isPending || updatePreset.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {(createPreset.isPending || updatePreset.isPending) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Check size={12} />
              )}
              {t('prompt_presets_tab.save')}
            </button>
            <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
              <X size={12} /> {t('prompt_presets_tab.cancel')}
            </button>
          </div>
        </div>
      )}

      {presets.map((p) => (
        <div
          key={p.id}
          className="rounded-lg p-4 space-y-2"
          style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              {p.is_default === 1 && (
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                >
                  {t('prompt_presets_tab.default_badge')}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => startEdit(p)}
                className="p-1.5 rounded transition-all duration-150"
                style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', backgroundColor: 'var(--bg-primary)' }}
                title={t('prompt_presets_tab.edit_preset')}
              >
                <Edit2 size={12} />
              </button>
              {presets.length > 1 && (
                <button
                  onClick={() => handleDelete(p.id)}
                  disabled={deletePreset.isPending}
                  className="p-1.5 rounded transition-all duration-150"
                  style={{ border: '1px solid var(--border)', color: 'var(--error)', backgroundColor: 'var(--bg-primary)' }}
                  title={t('prompt_presets_tab.delete_preset')}
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
          {editingId === p.id ? (
            <div className="space-y-2">
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
                className="w-full px-3 py-2 rounded-md text-sm"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
              <textarea
                value={formData.prompt_template}
                onChange={(e) => setFormData((f) => ({ ...f, prompt_template: e.target.value }))}
                rows={8}
                className="w-full px-3 py-2 rounded-md text-sm font-mono"
                style={{
                  backgroundColor: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                }}
              />
              <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData((f) => ({ ...f, is_default: e.target.checked }))}
                />
                {t('prompt_presets_tab.set_as_default')}
              </label>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSave}
                  disabled={updatePreset.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {updatePreset.isPending ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : (
                    <Check size={12} />
                  )}
                  {t('prompt_presets_tab.save')}
                </button>
                <button onClick={resetForm} className="flex items-center gap-1 px-3 py-1.5 rounded text-xs" style={{ color: 'var(--text-muted)' }}>
                  <X size={12} /> {t('prompt_presets_tab.cancel')}
                </button>
              </div>
            </div>
          ) : (
            <div
              className="rounded px-3 py-2 text-xs font-mono max-h-32 overflow-auto"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap',
              }}
            >
              {p.prompt_template}
            </div>
          )}
        </div>
      ))}

      {presets.length === 0 && !showAdd && (
        <div className="text-center py-8 text-sm" style={{ color: 'var(--text-muted)' }}>
          {t('prompt_presets_tab.no_presets')}
        </div>
      )}
    </div>
  )
}
