import { useState } from 'react'
import {
  useWatchedFolders,
  useSaveWatchedFolder,
  useDeleteWatchedFolder,
  useTriggerStandaloneScan,
  useStandaloneStatus,
} from '@/hooks/useApi'
import {
  Loader2,
  Trash2,
  Plus,
  Edit2,
  X,
  Check,
  FolderOpen,
  RefreshCw,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/components/shared/Toast'
import type { WatchedFolder } from '@/lib/types'
import type { FieldConfig } from './settingsFields'
import { SettingRow } from '@/components/shared/SettingRow'
import { Toggle } from '@/components/shared/Toggle'

// ─── Library Sources Tab (Standalone Mode) ──────────────────────────────────

export function LibrarySourcesTab({
  values,
  onFieldChange,
  fields,
}: {
  values: Record<string, string>
  onFieldChange: (key: string, value: string) => void
  fields: FieldConfig[]
}) {
  const { t } = useTranslation('settings')
  const { data: folders, isLoading: foldersLoading } = useWatchedFolders()
  const saveFolder = useSaveWatchedFolder()
  const removeFolder = useDeleteWatchedFolder()
  const scanAll = useTriggerStandaloneScan()
  const { data: standaloneStatus } = useStandaloneStatus()
  const [showAdd, setShowAdd] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newMediaType, setNewMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editPath, setEditPath] = useState('')
  const [editLabel, setEditLabel] = useState('')
  const [editMediaType, setEditMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')

  const tabFields = fields.filter((f) => f.tab === 'Library Sources')

  const handleAddFolder = () => {
    if (!newPath.trim()) return
    saveFolder.mutate(
      { path: newPath.trim(), label: newLabel.trim(), media_type: newMediaType, enabled: true },
      {
        onSuccess: () => {
          setNewPath('')
          setNewLabel('')
          setNewMediaType('auto')
          setShowAdd(false)
          toast(t('library_sources.folder_added'))
        },
        onError: () => toast(t('library_sources.folder_add_failed'), 'error'),
      },
    )
  }

  const handleEditFolder = (folder: WatchedFolder) => {
    setEditingId(folder.id)
    setEditPath(folder.path)
    setEditLabel(folder.label)
    setEditMediaType(folder.media_type)
  }

  const handleSaveEdit = () => {
    if (!editingId || !editPath.trim()) return
    saveFolder.mutate(
      { id: editingId, path: editPath.trim(), label: editLabel.trim(), media_type: editMediaType },
      {
        onSuccess: () => {
          setEditingId(null)
          toast(t('library_sources.folder_updated'))
        },
        onError: () => toast(t('library_sources.folder_update_failed'), 'error'),
      },
    )
  }

  const handleToggleEnabled = (folder: WatchedFolder) => {
    saveFolder.mutate(
      { id: folder.id, path: folder.path, enabled: !folder.enabled },
    )
  }

  const handleDelete = (folderId: number) => {
    removeFolder.mutate(folderId, {
      onSuccess: () => toast(t('library_sources.folder_removed')),
      onError: () => toast(t('library_sources.folder_remove_failed'), 'error'),
    })
  }

  const handleScanAll = () => {
    scanAll.mutate(undefined, {
      onSuccess: () => toast(t('library_sources.scan_started')),
      onError: () => toast(t('library_sources.scan_failed'), 'error'),
    })
  }

  const selectStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: '13px',
  }

  return (
    <div
      className="rounded-lg p-5 space-y-5"
      style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
    >
      {/* Config fields — SettingRow handles advanced/showAdvanced filtering internally */}
      {tabFields.map((field) => (
        <SettingRow
          key={field.key}
          label={field.label}
          description={field.description}
          advanced={field.advanced}
        >
          {field.type === 'toggle' ? (
            <Toggle
              checked={values[field.key] === 'true'}
              onChange={(v) => onFieldChange(field.key, String(v))}
            />
          ) : (
            <input
              type={field.type}
              value={values[field.key] === '***configured***' ? '' : (values[field.key] ?? '')}
              onChange={(e) => onFieldChange(field.key, e.target.value)}
              placeholder={values[field.key] === '***configured***' ? '(configured -- enter new value to change)' : field.placeholder}
              className="w-full px-3 py-2 rounded-md text-sm transition-all duration-150 focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: field.type === 'text' ? 'var(--font-mono)' : undefined,
                fontSize: '13px',
              }}
            />
          )}
        </SettingRow>
      ))}

      {/* Watched Folders section */}
      <div className="pt-4 space-y-3" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FolderOpen size={16} style={{ color: 'var(--accent)' }} />
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
              {t('library_sources.watched_folders')}
            </h3>
            {standaloneStatus && (
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium"
                style={{
                  backgroundColor: standaloneStatus.watcher_running ? 'var(--success-bg)' : 'rgba(124,130,147,0.08)',
                  color: standaloneStatus.watcher_running ? 'var(--success)' : 'var(--text-muted)',
                }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: standaloneStatus.watcher_running ? 'var(--success)' : 'var(--text-muted)' }}
                />
                {standaloneStatus.watcher_running ? t('library_sources.watcher_watching') : t('library_sources.watcher_stopped')}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleScanAll}
              disabled={scanAll.isPending || standaloneStatus?.scanner_scanning}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150 disabled:opacity-60"
              style={{
                border: '1px solid var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'var(--bg-primary)',
              }}
              title={t('library_sources_tab.scan_all')}
            >
              {(scanAll.isPending || standaloneStatus?.scanner_scanning) ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <RefreshCw size={12} />
              )}
              {standaloneStatus?.scanner_scanning ? t('library_sources.scanning') : t('library_sources.scan_all')}
            </button>
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
              style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
            >
              <Plus size={12} />
              {t('library_sources.add_folder')}
            </button>
          </div>
        </div>

        {/* Folder list */}
        {foldersLoading ? (
          <div className="flex items-center justify-center py-4">
            <Loader2 size={16} className="animate-spin" style={{ color: 'var(--accent)' }} />
          </div>
        ) : (
          <div className="space-y-2">
            {folders && folders.length > 0 ? (
              folders.map((folder) => (
                <div
                  key={folder.id}
                  className="rounded-lg p-3 space-y-2"
                  style={{
                    backgroundColor: 'var(--bg-primary)',
                    border: '1px solid var(--border)',
                    opacity: folder.enabled ? 1 : 0.6,
                  }}
                >
                  {editingId === folder.id ? (
                    /* Edit mode */
                    <div className="space-y-2">
                      <input
                        type="text"
                        value={editPath}
                        onChange={(e) => setEditPath(e.target.value)}
                        placeholder="/path/to/media"
                        className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          border: '1px solid var(--border)',
                          color: 'var(--text-primary)',
                          fontFamily: 'var(--font-mono)',
                          fontSize: '13px',
                        }}
                      />
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          placeholder={t('library_sources.label_placeholder')}
                          className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                          style={{
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border)',
                            color: 'var(--text-primary)',
                            fontSize: '13px',
                          }}
                        />
                        <select
                          value={editMediaType}
                          onChange={(e) => setEditMediaType(e.target.value as 'auto' | 'tv' | 'movie')}
                          className="px-2.5 py-1.5 rounded text-sm focus:outline-none"
                          style={selectStyle}
                        >
                          <option value="auto">Auto</option>
                          <option value="tv">TV</option>
                          <option value="movie">{t('library_sources_tab.movie')}</option>
                        </select>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleSaveEdit}
                          disabled={saveFolder.isPending}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white"
                          style={{ backgroundColor: 'var(--accent)' }}
                        >
                          {saveFolder.isPending ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                          Save
                        </button>
                        <button
                          onClick={() => setEditingId(null)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded text-xs"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          <X size={10} />
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Display mode */
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className="text-sm truncate"
                            style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }}
                            title={folder.path}
                          >
                            {folder.path}
                          </span>
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                            style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                          >
                            {folder.media_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          {folder.label && <span>{folder.label}</span>}
                          {folder.last_scan_at && (
                            <span>{t('library_sources.last_scan')} {new Date(folder.last_scan_at).toLocaleString()}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => handleToggleEnabled(folder)}
                          className="px-2 py-1 rounded text-[10px] font-medium transition-all duration-150"
                          style={{
                            backgroundColor: folder.enabled ? 'var(--accent-bg)' : 'var(--bg-surface)',
                            color: folder.enabled ? 'var(--accent)' : 'var(--text-muted)',
                            border: '1px solid ' + (folder.enabled ? 'var(--accent-dim)' : 'var(--border)'),
                          }}
                        >
                          {folder.enabled ? t('library_sources.folder_enabled') : t('library_sources.folder_disabled')}
                        </button>
                        <button
                          onClick={() => handleEditFolder(folder)}
                          className="p-1.5 rounded transition-all duration-150"
                          style={{ color: 'var(--text-muted)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
                          title={t('library_sources_tab.edit_folder')}
                        >
                          <Edit2 size={12} />
                        </button>
                        <button
                          onClick={() => handleDelete(folder.id)}
                          className="p-1.5 rounded transition-all duration-150"
                          style={{ color: 'var(--text-muted)', border: '1px solid var(--border)', backgroundColor: 'var(--bg-surface)' }}
                          title={t('library_sources_tab.remove_folder')}
                          onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
                {t('library_sources.no_folders')}
              </div>
            )}
          </div>
        )}

        {/* Add folder form */}
        {showAdd && (
          <div
            className="rounded-lg p-3 space-y-2"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--accent-dim)' }}
          >
            <input
              type="text"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="/path/to/media"
              className="w-full px-2.5 py-1.5 rounded text-sm focus:outline-none"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
              }}
              autoFocus
            />
            <div className="flex gap-2">
              <input
                type="text"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
                placeholder={t('library_sources_tab.label_optional')}
                className="flex-1 px-2.5 py-1.5 rounded text-sm focus:outline-none"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: '13px',
                }}
              />
              <select
                value={newMediaType}
                onChange={(e) => setNewMediaType(e.target.value as 'auto' | 'tv' | 'movie')}
                className="px-2.5 py-1.5 rounded text-sm focus:outline-none"
                style={selectStyle}
              >
                <option value="auto">Auto</option>
                <option value="tv">TV</option>
                <option value="movie">{t('library_sources_tab.movie')}</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleAddFolder}
                disabled={saveFolder.isPending || !newPath.trim()}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-white"
                style={{ backgroundColor: 'var(--accent)' }}
              >
                {saveFolder.isPending ? <Loader2 size={10} className="animate-spin" /> : <Check size={10} />}
                Save
              </button>
              <button
                onClick={() => { setShowAdd(false); setNewPath(''); setNewLabel(''); setNewMediaType('auto') }}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                <X size={10} />
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
