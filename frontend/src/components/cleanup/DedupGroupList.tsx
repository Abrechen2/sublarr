/**
 * DedupGroupList -- Displays grouped duplicate subtitle files with keep/delete selection.
 *
 * Each group shows files sharing the same content hash. Users select which file
 * to keep (radio) and which to delete (checkboxes). Delete button is disabled
 * until exactly one file per group is marked as KEEP.
 */
import { useState, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2, FileText, Check } from 'lucide-react'
import type { DuplicateGroup } from '@/lib/types'

interface DedupGroupListProps {
  groups: DuplicateGroup[]
  onDelete: (selections: { keep: string; delete: string[] }[]) => void
  isDeleting?: boolean
}

/** Format bytes into human-readable KB/MB/GB */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / Math.pow(1024, i)
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/** Truncate a file path keeping the filename visible */
function truncatePath(path: string, maxLen = 60): string {
  if (path.length <= maxLen) return path
  const parts = path.replace(/\\/g, '/').split('/')
  const filename = parts[parts.length - 1]
  if (filename.length >= maxLen - 3) return '...' + filename.slice(-(maxLen - 3))
  const available = maxLen - filename.length - 4 // 4 = ".../"
  const prefix = parts.slice(0, -1).join('/')
  return prefix.slice(0, available) + '.../' + filename
}

interface GroupSelection {
  keepPath: string
  deletePaths: Set<string>
}

export function DedupGroupList({ groups, onDelete, isDeleting = false }: DedupGroupListProps) {
  const { t } = useTranslation('settings')

  // Initialize selections: first file in each group is KEEP by default, rest are DELETE
  const [selections, setSelections] = useState<Record<string, GroupSelection>>(() => {
    const init: Record<string, GroupSelection> = {}
    for (const group of groups) {
      if (group.files.length > 1) {
        init[group.content_hash] = {
          keepPath: group.files[0].file_path,
          deletePaths: new Set(group.files.slice(1).map((f) => f.file_path)),
        }
      }
    }
    return init
  })

  const handleKeepChange = useCallback((hash: string, path: string, allPaths: string[]) => {
    setSelections((prev) => ({
      ...prev,
      [hash]: {
        keepPath: path,
        deletePaths: new Set(allPaths.filter((p) => p !== path)),
      },
    }))
  }, [])

  const handleDeleteToggle = useCallback((hash: string, path: string) => {
    setSelections((prev) => {
      const current = prev[hash]
      if (!current) return prev
      const next = new Set(current.deletePaths)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return { ...prev, [hash]: { ...current, deletePaths: next } }
    })
  }, [])

  // Check if all groups have valid selections (exactly one KEEP, at least one DELETE)
  const allValid = useMemo(() => {
    return groups.every((group) => {
      if (group.files.length <= 1) return true
      const sel = selections[group.content_hash]
      return sel && sel.keepPath && sel.deletePaths.size > 0
    })
  }, [groups, selections])

  const handleBatchDelete = useCallback(() => {
    const batchSelections = groups
      .filter((g) => g.files.length > 1 && selections[g.content_hash]?.deletePaths.size > 0)
      .map((g) => {
        const sel = selections[g.content_hash]
        return {
          keep: sel.keepPath,
          delete: Array.from(sel.deletePaths),
        }
      })
    if (batchSelections.length > 0) {
      onDelete(batchSelections)
    }
  }, [groups, selections, onDelete])

  const totalDeletable = useMemo(() => {
    return Object.values(selections).reduce((sum, sel) => sum + sel.deletePaths.size, 0)
  }, [selections])

  if (groups.length === 0) {
    return (
      <div
        className="text-center py-8 text-sm"
        style={{ color: 'var(--text-muted)' }}
      >
        {t('cleanup.dedup.noResults', 'No duplicate groups found')}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Batch delete header */}
      <div className="flex items-center justify-between">
        <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {groups.length} {t('cleanup.dedup.groupsFound', 'duplicate groups')} ({totalDeletable} {t('cleanup.dedup.filesToDelete', 'files to delete')})
        </span>
        <button
          onClick={handleBatchDelete}
          disabled={!allValid || isDeleting || totalDeletable === 0}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-opacity disabled:opacity-40"
          style={{ backgroundColor: 'var(--error)' }}
        >
          <Trash2 size={12} />
          {isDeleting
            ? t('cleanup.dedup.deleting', 'Deleting...')
            : t('cleanup.dedup.deleteAll', 'Delete All Selected')}
        </button>
      </div>

      {/* Group cards */}
      {groups.map((group) => {
        const sel = selections[group.content_hash]
        const allPaths = group.files.map((f) => f.file_path)

        return (
          <div
            key={group.content_hash}
            className="rounded-lg p-4 space-y-3"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}
          >
            {/* Group header */}
            <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
              <FileText size={12} />
              <code style={{ fontFamily: 'var(--font-mono)' }}>
                {group.content_hash.slice(0, 12)}...
              </code>
              <span className="ml-auto">
                {group.files.length} {t('cleanup.dedup.files', 'files')}
              </span>
            </div>

            {/* File list */}
            <div className="space-y-2">
              {group.files.map((file) => {
                const isKeep = sel?.keepPath === file.file_path
                const isDelete = sel?.deletePaths.has(file.file_path) ?? false

                return (
                  <div
                    key={file.file_path}
                    className="flex items-center gap-3 px-3 py-2 rounded-md"
                    style={{
                      backgroundColor: isKeep ? 'var(--accent-bg)' : isDelete ? 'rgba(239,68,68,0.05)' : 'var(--bg-primary)',
                      border: `1px solid ${isKeep ? 'var(--accent-dim)' : 'var(--border)'}`,
                    }}
                  >
                    {/* Keep radio */}
                    <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                      <input
                        type="radio"
                        name={`keep-${group.content_hash}`}
                        checked={isKeep}
                        onChange={() => handleKeepChange(group.content_hash, file.file_path, allPaths)}
                        className="accent-[var(--accent)]"
                      />
                      <span className="text-xs font-medium" style={{ color: isKeep ? 'var(--accent)' : 'var(--text-muted)' }}>
                        {isKeep ? t('cleanup.dedup.keepLabel', 'Keep') : t('cleanup.dedup.keepLabel', 'Keep')}
                      </span>
                    </label>

                    {/* Delete checkbox */}
                    {!isKeep && (
                      <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                        <input
                          type="checkbox"
                          checked={isDelete}
                          onChange={() => handleDeleteToggle(group.content_hash, file.file_path)}
                          className="accent-[var(--error)]"
                        />
                        <span className="text-xs" style={{ color: isDelete ? 'var(--error)' : 'var(--text-muted)' }}>
                          {t('cleanup.dedup.deleteLabel', 'Delete')}
                        </span>
                      </label>
                    )}

                    {isKeep && (
                      <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--accent)' }}>
                        <Check size={10} />
                      </span>
                    )}

                    {/* File info */}
                    <div className="flex-1 min-w-0">
                      <div
                        className="text-xs truncate"
                        style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}
                        title={file.file_path}
                      >
                        {truncatePath(file.file_path)}
                      </div>
                    </div>

                    {/* Badges */}
                    <div className="flex items-center gap-2 shrink-0">
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                        style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}
                      >
                        {file.format}
                      </span>
                      {file.language && (
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}
                        >
                          {file.language}
                        </span>
                      )}
                      <span className="text-xs tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
                        {formatBytes(file.file_size)}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
