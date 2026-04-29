/**
 * StandaloneFolderManager — Watched-folder CRUD UI for Standalone-Modus.
 *
 * Replaces the orphan LibrarySourcesTab. Renders inside ConnectionsMediaServers'
 * StandaloneSection so the entire standalone-mode bedienpfad lives in a single
 * Settings → Connections section instead of two competing locations.
 *
 * Includes:
 *   - standalone_enabled Toggle (with auto_activated hint, F4)
 *   - Watched-folder list (path, label, type, last_scan_at, enabled toggle)
 *   - Add / edit / delete actions
 *   - Per-folder scan trigger (F3)
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Loader2,
  Trash2,
  Plus,
  Edit2,
  X,
  Check,
  Play,
} from 'lucide-react'
import {
  useWatchedFolders,
  useSaveWatchedFolder,
  useDeleteWatchedFolder,
  useTriggerStandaloneFolderScan,
  useStandaloneStatus,
  useConfig,
  useUpdateConfig,
} from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import { Toggle } from '@/components/shared/Toggle'
import { boolVal } from '@/lib/configUtils'
import type { WatchedFolder } from '@/lib/types'

export function StandaloneFolderManager() {
  const { t } = useTranslation('settings')
  const { data: folders, isLoading: foldersLoading } = useWatchedFolders()
  const { data: config } = useConfig()
  const updateConfig = useUpdateConfig()
  const saveFolder = useSaveWatchedFolder()
  const removeFolder = useDeleteWatchedFolder()
  const scanFolder = useTriggerStandaloneFolderScan()
  const { data: standaloneStatus } = useStandaloneStatus()

  const [showAdd, setShowAdd] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newMediaType, setNewMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editPath, setEditPath] = useState('')
  const [editLabel, setEditLabel] = useState('')
  const [editMediaType, setEditMediaType] = useState<'auto' | 'tv' | 'movie'>('auto')

  const isAutoActivated = standaloneStatus?.auto_activated === true
  const standaloneEnabled = boolVal(config, 'standalone_enabled', false)

  const handleToggleStandalone = (v: boolean) => {
    updateConfig.mutate(
      { standalone_enabled: v },
      {
        onSuccess: () => toast(t('setting_saved')),
        onError: () => toast(t('setting_save_failed'), 'error'),
      },
    )
  }

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
    saveFolder.mutate({ id: folder.id, path: folder.path, enabled: !folder.enabled })
  }

  const handleDelete = (folderId: number) => {
    removeFolder.mutate(folderId, {
      onSuccess: () => toast(t('library_sources.folder_removed')),
      onError: () => toast(t('library_sources.folder_remove_failed'), 'error'),
    })
  }

  const handleScanFolder = (folderId: number) => {
    scanFolder.mutate(folderId, {
      onSuccess: () => toast(t('library_sources.folder_scan_started')),
      onError: () => toast(t('library_sources.folder_scan_failed'), 'error'),
    })
  }

  const selectStyle = {
    backgroundColor: 'var(--bg-primary)',
    border: '1px solid var(--border)',
    color: 'var(--text-primary)',
    fontSize: '13px',
  }

  return (
    <div className="space-y-4">
      {/* standalone_enabled toggle with F4 auto_activated hint */}
      <div
        className="flex items-start justify-between gap-4 rounded-lg p-3"
        style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)' }}
      >
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {t('library_sources.enable_standalone', 'Standalone-Modus aktivieren')}
          </div>
          <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
            {isAutoActivated
              ? t('library_sources.standalone_auto_activated_hint')
              : t('library_sources.enable_standalone_desc',
                  'Direktes Dateisystem-Scanning ohne Sonarr/Radarr.')}
          </div>
        </div>
        <Toggle
          checked={isAutoActivated ? true : standaloneEnabled}
          onChange={handleToggleStandalone}
          disabled={isAutoActivated || updateConfig.isPending}
        />
      </div>

      {/* Folder list header + add button */}
      <div className="flex items-center justify-between pt-2">
        <h4 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          {t('library_sources.watched_folders')}
        </h4>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-xs font-medium transition-all duration-150"
          style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)' }}
        >
          <Plus size={12} />
          {t('library_sources.add_folder')}
        </button>
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
                        onClick={() => handleScanFolder(folder.id)}
                        disabled={!folder.enabled || scanFolder.isPending || standaloneStatus?.scanner_scanning}
                        className="p-1.5 rounded transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ color: 'var(--accent)', border: '1px solid var(--accent-dim)', backgroundColor: 'var(--bg-surface)' }}
                        title={t('library_sources_tab.scan_folder')}
                      >
                        {scanFolder.isPending && scanFolder.variables === folder.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Play size={12} />
                        )}
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
  )
}
