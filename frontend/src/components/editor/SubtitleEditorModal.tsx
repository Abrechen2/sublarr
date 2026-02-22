/**
 * SubtitleEditorModal -- Modal wrapper with lazy loading and mode switching.
 *
 * Lazy-loads SubtitlePreview, SubtitleEditor, and SubtitleDiff to keep
 * CodeMirror out of the main bundle. Manages mode transitions (preview/edit/diff)
 * and provides the shared content state needed by editor and diff views.
 */

import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { Loader2, X, Eye, Pencil, GitCompare, RefreshCw, Activity } from 'lucide-react'
import { useSubtitleContent } from '@/hooks/useApi'
import { autoSyncFile, overlapFix, timingNormalize, mergeLines, splitLines, spellCheck } from '@/api/client'
import { toast } from '@/components/shared/Toast'

// Lazy-loaded editor components -- CodeMirror stays in separate chunks
const SubtitlePreview = lazy(() => import('@/components/editor/SubtitlePreview'))
const SubtitleEditor = lazy(() =>
  import('@/components/editor/SubtitleEditor').then(m => ({ default: m.SubtitleEditor }))
)
const SubtitleDiff = lazy(() =>
  import('@/components/editor/SubtitleDiff').then(m => ({ default: m.SubtitleDiff }))
)
const WaveformTab = lazy(() =>
  import('@/components/editor/WaveformTab').then(m => ({ default: m.WaveformTab }))
)

type EditorMode = 'preview' | 'edit' | 'diff' | 'waveform'

interface SubtitleEditorModalProps {
  filePath: string | null         // null = modal closed
  initialMode?: EditorMode
  onClose: () => void
  videoPath?: string              // optional: enables Waveform tab
}

/** Truncate a file path for display, showing last 2 segments. */
function truncateFilePath(path: string, maxLen = 60): string {
  if (path.length <= maxLen) return path
  const parts = path.replace(/\\/g, '/').split('/')
  if (parts.length <= 2) return path
  const tail = parts.slice(-2).join('/')
  return tail.length <= maxLen ? `.../${tail}` : `...${path.slice(-maxLen)}`
}

export default function SubtitleEditorModal({
  filePath,
  initialMode = 'preview',
  onClose,
  videoPath,
}: SubtitleEditorModalProps) {
  const [mode, setMode] = useState<EditorMode>(initialMode)
  const [content, setContent] = useState<string | null>(null)
  const [lastModified, setLastModified] = useState<number | null>(null)
  const [format, setFormat] = useState<'ass' | 'srt' | null>(null)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [syncLoading, setSyncLoading] = useState(false)
  const overlayRef = useRef<HTMLDivElement>(null)

  // Reset state when filePath or initialMode changes
  useEffect(() => {
    setMode(initialMode)
    setContent(null)
    setLastModified(null)
    setFormat(null)
    setHasUnsavedChanges(false)
  }, [filePath, initialMode])

  // Load subtitle content
  const { data: contentData } = useSubtitleContent(filePath)

  // Store loaded content into local state
  useEffect(() => {
    if (contentData) {
      setContent(contentData.content)
      setLastModified(contentData.last_modified)
      setFormat(contentData.format)
    }
  }, [contentData])

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (!filePath) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [filePath])

  // Handle Escape key
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      if (hasUnsavedChanges) {
        if (!confirm('You have unsaved changes. Close without saving?')) return
      }
      onClose()
    }
  }, [hasUnsavedChanges, onClose])

  useEffect(() => {
    if (!filePath) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [filePath, handleKeyDown])

  // Handle overlay click (close if no unsaved changes)
  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) {
      if (hasUnsavedChanges) {
        if (!confirm('You have unsaved changes. Close without saving?')) return
      }
      onClose()
    }
  }, [hasUnsavedChanges, onClose])

  // Close handler with unsaved changes guard
  const handleClose = useCallback(() => {
    if (hasUnsavedChanges) {
      if (!confirm('You have unsaved changes. Close without saving?')) return
    }
    onClose()
  }, [hasUnsavedChanges, onClose])

  // Auto-sync timing via alass/ffsubsync
  const handleAutoSync = () => {
    if (!filePath) return
    setSyncLoading(true)
    autoSyncFile(filePath)
      .then(() => {
        toast('Auto-sync complete')
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Auto-sync failed'
        toast(msg, 'error')
      })
      .finally(() => setSyncLoading(false))
  }

  // Quality fix state and handlers
  const [fixLoading, setFixLoading] = useState<string | null>(null)

  const runFix = useCallback((name: string, fn: () => Promise<string>) => {
    if (fixLoading || !filePath) return
    setFixLoading(name)
    fn()
      .then((msg) => { toast(msg) })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : `${name} fehlgeschlagen`
        toast(msg, 'error')
      })
      .finally(() => setFixLoading(null))
  }, [fixLoading, filePath])

  const qualityFixes = [
    { key: 'overlap', label: 'Überlappungen', fn: () => overlapFix(filePath!).then(r => `${r.fixed} Überlappungen behoben`) },
    { key: 'timing', label: 'Timing', fn: () => timingNormalize(filePath!).then(r => `${r.extended} Cues verlängert, ${r.too_long} zu lang`) },
    { key: 'merge', label: 'Zusammenführen', fn: () => mergeLines(filePath!).then(r => `${r.merged} Zeilen zusammengeführt`) },
    { key: 'split', label: 'Aufteilen', fn: () => splitLines(filePath!).then(r => `${r.split} Cues aufgeteilt`) },
    { key: 'spell', label: 'Rechtschreibung', fn: () => spellCheck(filePath!).then(r => `${r.total} Fehler gefunden`) },
  ]

  // When modal is closed, render nothing
  if (!filePath) return null

  const MODE_TABS: { key: EditorMode; label: string; icon: typeof Eye }[] = [
    { key: 'preview', label: 'Preview', icon: Eye },
    { key: 'edit', label: 'Edit', icon: Pencil },
    { key: 'diff', label: 'Diff', icon: GitCompare },
    ...(videoPath ? [{ key: 'waveform' as const, label: 'Waveform', icon: Activity }] : []),
  ]

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
      onClick={handleOverlayClick}
    >
      <div
        className="w-[92vw] h-[88vh] max-w-7xl rounded-lg overflow-hidden flex flex-col"
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: '1px solid var(--border)',
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-2 flex-shrink-0"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            borderBottom: '1px solid var(--border)',
          }}
        >
          {/* Mode tabs */}
          <div className="flex items-center gap-1">
            {MODE_TABS.map(({ key, label, icon: Icon }) => {
              const isActive = mode === key
              return (
                <button
                  key={key}
                  onClick={() => setMode(key)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
                  style={{
                    backgroundColor: isActive ? 'var(--accent-bg)' : 'transparent',
                    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
                    border: isActive ? '1px solid var(--accent-dim)' : '1px solid transparent',
                  }}
                >
                  <Icon size={13} />
                  {label}
                </button>
              )
            })}
          </div>

          {/* Auto-sync button */}
          <button
            onClick={handleAutoSync}
            disabled={syncLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-50"
            style={{
              backgroundColor: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
              border: '1px solid var(--border)',
            }}
            title="Auto-sync subtitle timing with alass/ffsubsync"
          >
            {syncLoading
              ? <Loader2 size={12} className="animate-spin" />
              : <RefreshCw size={12} />}
            Auto-Sync
          </button>

          {/* File path + close */}
          <div className="flex items-center gap-3">
            <span
              className="text-xs truncate max-w-[300px]"
              style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
              title={filePath}
            >
              {truncateFilePath(filePath)}
            </span>
            {hasUnsavedChanges && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                style={{
                  backgroundColor: 'var(--warning-bg)',
                  color: 'var(--warning)',
                }}
              >
                Unsaved
              </span>
            )}
            <button
              onClick={handleClose}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
              title="Close (Esc)"
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Quality fix toolbar — visible in edit mode only */}
        {mode === 'edit' && (
          <div
            className="flex items-center gap-1 px-4 py-1.5 flex-shrink-0 flex-wrap"
            style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--bg-elevated)' }}
          >
            {qualityFixes.map(({ key, label, fn }) => (
              <button
                key={key}
                onClick={() => { runFix(label, fn) }}
                disabled={fixLoading !== null}
                className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border)',
                  opacity: fixLoading !== null ? 0.5 : 1,
                }}
              >
                {fixLoading === label && <Loader2 size={9} className="animate-spin" />}
                {label}
              </button>
            ))}
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-hidden">
          <Suspense
            fallback={
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <Loader2
                  className="animate-spin h-8 w-8"
                  style={{ color: 'var(--accent)' }}
                />
                <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  Loading editor...
                </span>
              </div>
            }
          >
            {mode === 'preview' && (
              <SubtitlePreview
                filePath={filePath}
                onEdit={() => setMode('edit')}
                onClose={handleClose}
              />
            )}

            {mode === 'edit' && content !== null && format !== null && lastModified !== null && (
              <SubtitleEditor
                filePath={filePath}
                initialContent={content}
                format={format}
                lastModified={lastModified}
                onSave={(newMtime) => {
                  setLastModified(newMtime)
                  setHasUnsavedChanges(false)
                }}
                onClose={handleClose}
                onDiffView={() => setMode('diff')}
              />
            )}

            {mode === 'edit' && (content === null || format === null || lastModified === null) && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <Loader2
                  className="animate-spin h-8 w-8"
                  style={{ color: 'var(--accent)' }}
                />
                <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  Loading content...
                </span>
              </div>
            )}

            {mode === 'diff' && content !== null && format !== null && (
              <SubtitleDiff
                filePath={filePath}
                currentContent={content}
                format={format}
                onClose={handleClose}
                onBackToEditor={() => setMode('edit')}
              />
            )}

            {mode === 'diff' && (content === null || format === null) && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <Loader2
                  className="animate-spin h-8 w-8"
                  style={{ color: 'var(--accent)' }}
                />
                <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  Loading content...
                </span>
              </div>
            )}

            {mode === 'waveform' && videoPath && filePath && (
              <WaveformTab
                subtitlePath={filePath}
                videoPath={videoPath}
              />
            )}
          </Suspense>
        </div>
      </div>
    </div>
  )
}
