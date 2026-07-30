/**
 * SubtitleEditorModal -- Modal wrapper with lazy loading and mode switching.
 *
 * Lazy-loads SubtitlePreview, SubtitleEditor, and SubtitleDiff to keep
 * CodeMirror out of the main bundle. Manages mode transitions (preview/edit/diff)
 * and provides the shared content state needed by editor and diff views.
 */

import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Loader2, X, Eye, Pencil, GitCompare, RefreshCw, Activity, Maximize2, Minimize2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useSubtitleContent, useSaveSubtitle } from '@/hooks/useApi'
import { autoSyncFile, overlapFix, timingNormalize, mergeLines, splitLines, spellCheck, removeCredits, detectOpeningEnding } from '@/api/client'
import { useConvertSubtitleFormat } from '@/hooks/useTranslationApi'
import { toast } from '@/components/shared/Toast'
import { useTranslation } from 'react-i18next'
import {
  applyCueTiming,
  UnsupportedFormatError,
} from '@/components/editor/waveform/applyCueTiming'
import {
  applyCueText,
  CueTextHasStylingError,
} from '@/components/editor/waveform/applyCueText'
import {
  clearDraft,
  loadDraft,
  pruneStaleDrafts,
  shouldOfferDraft,
  type EditorDraft,
} from '@/components/editor/editorDraft'
import { useEditorDraft } from '@/components/editor/useEditorDraft'
import type { CueTimingFix } from '@/components/editor/waveform/fixSafeDefects'
import type { SubtitleParseResult } from '@/types/system'

// Lazy-loaded editor components -- CodeMirror stays in separate chunks
const SubtitlePreview = lazy(() => import('@/components/editor/SubtitlePreview'))
const SubtitleEditor = lazy(() =>
  import('@/components/editor/SubtitleEditor').then(m => ({ default: m.SubtitleEditor }))
)
const SubtitleDiff = lazy(() =>
  import('@/components/editor/SubtitleDiff')
)
const WaveformEditor = lazy(() =>
  import('@/components/editor/waveform/WaveformEditor').then(m => ({ default: m.WaveformEditor }))
)

type EditorMode = 'preview' | 'edit' | 'diff' | 'waveform'

interface SubtitleEditorModalProps {
  filePath: string | null         // null = modal closed
  initialMode?: EditorMode
  onClose: () => void
  videoPath?: string              // optional: enables Waveform tab
  onSeekRequest?: (seconds: number) => void  // optional: seek the co-open player
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
  onSeekRequest,
}: SubtitleEditorModalProps) {
  const { t } = useTranslation('editor')
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<EditorMode>(initialMode)
  const [fullscreen, setFullscreen] = useState(false)
  const [content, setContent] = useState<string | null>(null)
  const [lastModified, setLastModified] = useState<number | null>(null)
  const [format, setFormat] = useState<'ass' | 'srt' | null>(null)
  // The on-disk content as we last knew it: updated on load + save success.
  // `hasUnsavedChanges` is derived from `content !== baselineContent` so an
  // undo back to the saved baseline correctly clears the dirty flag.
  const [baselineContent, setBaselineContent] = useState<string | null>(null)
  const hasUnsavedChanges = content !== null && content !== baselineContent
  const [syncLoading, setSyncLoading] = useState(false)
  const overlayRef = useRef<HTMLDivElement>(null)
  const [convertTarget, setConvertTarget] = useState<'ass' | 'srt' | 'vtt'>('srt')
  const convertMut = useConvertSubtitleFormat()
  const { mutate: saveMutate, isPending: saveInFlight } = useSaveSubtitle()
  // Plan B8 Task 11: track which cue is selected from the WaveformEditor's
  // perspective. `null` = nothing focused, so L/R click-set + S/D hotkeys
  // become no-ops until the user picks a cue.
  const [selectedCueIdx, setSelectedCueIdx] = useState<number | null>(null)
  // Waveform-tab undo/redo: each entry holds the content as it was BEFORE
  // a cue-timing edit. Pop -> restore, push current to the opposite stack.
  // Stays separate from the CodeMirror editor's internal undo stack — they
  // are different surfaces with different edit semantics.
  const [waveformUndoStack, setWaveformUndoStack] = useState<string[]>([])
  const [waveformRedoStack, setWaveformRedoStack] = useState<string[]>([])
  // Crash-recovery: a draft left behind by a crashed/killed session that is
  // offered for restore. Cleared on decision or when the file changes.
  const [offeredDraft, setOfferedDraft] = useState<EditorDraft | null>(null)

  // Reset state when filePath or initialMode changes — "adjust during render" pattern
  // avoids a double-render cycle that useEffect would cause for prop-derived state
  const [prevFilePath, setPrevFilePath] = useState(filePath)
  const [prevInitialMode, setPrevInitialMode] = useState(initialMode)
  if (filePath !== prevFilePath || initialMode !== prevInitialMode) {
    setPrevFilePath(filePath)
    setPrevInitialMode(initialMode)
    setMode(initialMode)
    setContent(null)
    setLastModified(null)
    setFormat(null)
    setBaselineContent(null)
    setSelectedCueIdx(null)
    setWaveformUndoStack([])
    setWaveformRedoStack([])
    setOfferedDraft(null)
  }

  // Plan B8 Task 11: WaveformEditor drag-end / click-set / S/D hotkey
  // commits land here. We rewrite the cue's timing inside the in-memory
  // text buffer so the user sees the change immediately in the CodeMirror
  // edit tab and can save it via the normal Save button. ASS/SRT only;
  // VTT and unknown formats are silently ignored (the editor falls back
  // to read-only behaviour for those — covered by useEffect below).
  const handleCueTimingChange = useCallback(
    (id: string, patch: { start: number; end: number }) => {
      const idx = Number.parseInt(id, 10)
      if (Number.isNaN(idx) || !content || !format) return
      try {
        const next = applyCueTiming({
          content,
          format,
          cueIndex: idx,
          start: patch.start,
          end: patch.end,
        })
        if (next === content) return
        // Push the PRE-edit content onto the undo stack; clear redo so
        // the user can't fork timelines after a fresh edit.
        setWaveformUndoStack((stack) => [...stack, content])
        setWaveformRedoStack([])
        setContent(next)
      } catch (err) {
        if (err instanceof UnsupportedFormatError) {
          toast(t('editor_modal.waveform_unsupported_format', { format }), 'info')
          return
        }
        // Index-out-of-range or malformed input — surface a polite toast and
        // leave content untouched.
        const msg = err instanceof Error ? err.message : t('editor_modal.cue_update_failed')
        toast(msg, 'error')
      }
    },
    [content, format, t],
  )

  // Inline cue-text edit from the WaveformCueList. Same undo/redo
  // contract as the timing-edit path: snapshot the pre-edit content,
  // clear redo, then write the patched content back.
  const handleCueTextChange = useCallback(
    (idx: number, text: string) => {
      if (!content || !format) return
      try {
        const next = applyCueText({ content, format, cueIndex: idx, text })
        if (next === content) return
        setWaveformUndoStack((stack) => [...stack, content])
        setWaveformRedoStack([])
        setContent(next)
      } catch (err) {
        if (err instanceof UnsupportedFormatError) {
          toast(t('editor_modal.waveform_unsupported_format', { format }), 'info')
          return
        }
        if (err instanceof CueTextHasStylingError) {
          toast(t('editor_modal.cue_has_styling'), 'info')
          return
        }
        const msg = err instanceof Error ? err.message : t('editor_modal.cue_update_failed')
        toast(msg, 'error')
      }
    },
    [content, format, t],
  )

  // One-click "fix safe defects": apply the whole batch as ONE atomic edit —
  // a single undo-stack entry restores the pre-batch content. Also patches
  // the cached parse result so regions, defect lanes, and the issue chip
  // reflect the fixed timings immediately (the parse query reads from disk
  // and would otherwise stay stale until save).
  const handleApplyTimingFixes = useCallback(
    (fixes: CueTimingFix[]) => {
      if (!content || !format || fixes.length === 0) return
      try {
        let next = content
        for (const fix of fixes) {
          next = applyCueTiming({
            content: next,
            format,
            cueIndex: fix.cueIndex,
            start: fix.after.start,
            end: fix.after.end,
          })
        }
        if (next === content) return
        setWaveformUndoStack((stack) => [...stack, content])
        setWaveformRedoStack([])
        setContent(next)
        queryClient.setQueryData<SubtitleParseResult>(
          ['subtitle-parse', filePath],
          (old) => {
            if (!old) return old
            const cues = [...old.cues]
            for (const fix of fixes) {
              const cue = cues[fix.cueIndex]
              if (cue) cues[fix.cueIndex] = { ...cue, start: fix.after.start, end: fix.after.end }
            }
            return { ...old, cues }
          },
        )
        toast(t('editor_modal.fix_defects_applied', { count: fixes.length }))
      } catch (err) {
        if (err instanceof UnsupportedFormatError) {
          toast(t('editor_modal.waveform_unsupported_format', { format }), 'info')
          return
        }
        const msg = err instanceof Error ? err.message : t('editor_modal.cue_update_failed')
        toast(msg, 'error')
      }
    },
    [content, format, filePath, queryClient, t],
  )

  const handleWaveformUndo = useCallback(() => {
    if (waveformUndoStack.length === 0 || content === null) return
    const prev = waveformUndoStack[waveformUndoStack.length - 1]
    setWaveformUndoStack((stack) => stack.slice(0, -1))
    setWaveformRedoStack((stack) => [...stack, content])
    setContent(prev)
  }, [waveformUndoStack, content])

  const handleWaveformRedo = useCallback(() => {
    if (waveformRedoStack.length === 0 || content === null) return
    const next = waveformRedoStack[waveformRedoStack.length - 1]
    setWaveformRedoStack((stack) => stack.slice(0, -1))
    setWaveformUndoStack((stack) => [...stack, content])
    setContent(next)
  }, [waveformRedoStack, content])

  const handleWaveformSave = useCallback(() => {
    if (!filePath || content === null || lastModified === null) return
    const snapshot = content
    saveMutate(
      { filePath, content: snapshot, lastModified },
      {
        onSuccess: (result) => {
          setLastModified(result.new_mtime)
          // Bump the baseline to what we just persisted so the dirty
          // flag (derived from content !== baselineContent) clears even
          // if `content` mutated again during the request.
          setBaselineContent(snapshot)
          // Save resets the dirty-state but keeps the undo stack so the
          // user can still roll back even after persisting.
          toast(t('editor_modal.saved'))
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : t('editor_modal.save_failed')
          toast(msg, 'error')
        },
      },
    )
  }, [filePath, content, lastModified, saveMutate, t])

  /** Move the WaveformEditor's selection by one cue (Up/Down hotkeys). */
  const handleSelectAdjacentCue = useCallback((direction: 'prev' | 'next') => {
    setSelectedCueIdx((cur) => {
      const base = cur ?? 0
      return direction === 'prev' ? Math.max(0, base - 1) : base + 1
      // Upper bound is enforced inside the WaveformEditor when it looks
      // up the cue by id; selecting past the end becomes a no-op.
    })
  }, [])

  // Load subtitle content
  const { data: contentData } = useSubtitleContent(filePath)

  // Sync server content into local state — "adjust during render" pattern
  const [prevContentData, setPrevContentData] = useState(contentData)
  if (contentData !== prevContentData) {
    setPrevContentData(contentData)
    if (contentData) {
      setContent(contentData.content)
      setBaselineContent(contentData.content)
      setLastModified(contentData.last_modified)
      setFormat(contentData.format)
      // Crash-recovery: offer a leftover draft, but only while the on-disk
      // mtime still matches what the draft was based on — restoring against
      // a file that changed since would let a later save clobber it.
      if (filePath) {
        const draft = loadDraft(filePath)
        setOfferedDraft(
          shouldOfferDraft(draft, contentData.last_modified, contentData.content) ? draft : null
        )
      }
    }
  }

  // Mirror dirty edits into localStorage (debounced) so a crash loses ~1s of
  // work at most; cleans the draft up again on save / undo-to-baseline.
  useEditorDraft(filePath, content, lastModified, hasUnsavedChanges)

  // Housekeeping: drop drafts older than 14 days once per opened file.
  useEffect(() => {
    if (filePath) pruneStaleDrafts()
  }, [filePath])

  const handleDraftRestore = useCallback(() => {
    if (!offeredDraft || content === null) return
    // Same undo contract as any waveform edit: snapshot the pre-restore
    // content so the restore itself is undoable.
    setWaveformUndoStack((stack) => [...stack, content])
    setWaveformRedoStack([])
    setContent(offeredDraft.content)
    setOfferedDraft(null)
    toast(t('editor_modal.draft_restored'))
  }, [offeredDraft, content, t])

  const handleDraftDiscard = useCallback(() => {
    if (filePath) clearDraft(filePath)
    setOfferedDraft(null)
  }, [filePath])

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (!filePath) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [filePath])

  // Handle Escape (exit fullscreen first, else close) + 'f' fullscreen toggle.
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      if (fullscreen) {
        setFullscreen(false)
        return
      }
      if (hasUnsavedChanges) {
        if (!confirm(t('editor_modal.unsaved_confirm'))) return
      }
      onClose()
      return
    }
    // 'f' toggles fullscreen — but never while the user is typing (CodeMirror,
    // inputs, textareas, contenteditable) so it doesn't swallow the character.
    if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const el = e.target as HTMLElement | null
      if (
        el &&
        (el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.isContentEditable ||
          el.closest?.('.cm-editor'))
      ) {
        return
      }
      e.preventDefault()
      setFullscreen((v) => !v)
    }
  }, [fullscreen, hasUnsavedChanges, onClose, t])

  useEffect(() => {
    if (!filePath) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [filePath, handleKeyDown])

  // Handle overlay click (close if no unsaved changes)
  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === overlayRef.current) {
      if (hasUnsavedChanges) {
        if (!confirm(t('editor_modal.unsaved_confirm'))) return
      }
      onClose()
    }
  }, [hasUnsavedChanges, onClose, t])

  // Close handler with unsaved changes guard
  const handleClose = useCallback(() => {
    if (hasUnsavedChanges) {
      if (!confirm(t('editor_modal.unsaved_confirm'))) return
    }
    onClose()
  }, [hasUnsavedChanges, onClose, t])

  // Auto-sync timing via alass/ffsubsync
  const handleAutoSync = () => {
    if (!filePath) return
    setSyncLoading(true)
    autoSyncFile(filePath)
      .then(() => {
        toast(t('editor_modal.autosync_complete'))
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : t('editor_modal.autosync_failed')
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
      .then((msg) => {
        toast(msg)
        void queryClient.invalidateQueries({ queryKey: ['subtitle-content', filePath] })
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : t('editor_modal.fix_failed', { name })
        toast(msg, 'error')
      })
      .finally(() => setFixLoading(null))
  }, [fixLoading, filePath, queryClient, t])

  const qualityFixes = [
    { key: 'overlap', label: t('editor_modal.fix_overlap'), fn: () => overlapFix(filePath!).then(r => t('editor_modal.fix_overlap_result', { count: r.fixed })) },
    { key: 'timing', label: t('editor_modal.fix_timing'), fn: () => timingNormalize(filePath!).then(r => t('editor_modal.fix_timing_result', { extended: r.extended, tooLong: r.too_long })) },
    { key: 'merge', label: t('editor_modal.fix_merge'), fn: () => mergeLines(filePath!).then(r => t('editor_modal.fix_merge_result', { count: r.merged })) },
    { key: 'split', label: t('editor_modal.fix_split'), fn: () => splitLines(filePath!).then(r => t('editor_modal.fix_split_result', { count: r.split })) },
    { key: 'spell', label: t('editor_modal.fix_spell'), fn: () => spellCheck(filePath!).then(r => t('editor_modal.fix_spell_result', { count: r.total })) },
    { key: 'credits', label: t('editor_modal.fix_credits'), fn: () => removeCredits(filePath!).then(r => t('editor_modal.fix_credits_result', { count: r.removed ?? 0 })) },
    { key: 'opEd', label: t('editor_modal.fix_oped'), fn: () => detectOpeningEnding(filePath!).then(r => r.detected.length > 0 ? t('editor_modal.fix_oped_result', { count: r.detected.length }) : t('editor_modal.fix_oped_none')) },
  ]

  // When modal is closed, render nothing
  if (!filePath) return null

  const MODE_TABS: { key: EditorMode; label: string; icon: typeof Eye }[] = [
    { key: 'preview', label: t('editor_modal.tab_preview'), icon: Eye },
    { key: 'edit', label: t('editor_modal.tab_edit'), icon: Pencil },
    { key: 'diff', label: t('editor_modal.tab_diff'), icon: GitCompare },
    ...(videoPath ? [{ key: 'waveform' as const, label: t('editor_modal.tab_waveform'), icon: Activity }] : []),
  ]

  return createPortal(
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.6)' }}
      onClick={handleOverlayClick}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('editor_modal.title')}
        className={
          fullscreen
            ? 'w-screen h-screen overflow-hidden flex flex-col'
            : 'w-[92vw] h-[88vh] max-w-7xl rounded-lg overflow-hidden flex flex-col'
        }
        style={{
          backgroundColor: 'var(--bg-surface)',
          border: fullscreen ? 'none' : '1px solid var(--border)',
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
            title={t('editor_modal.auto_sync_tooltip')}
          >
            {syncLoading
              ? <Loader2 size={12} className="animate-spin" />
              : <RefreshCw size={12} />}
            {t('editor_modal.auto_sync_button')}
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
                {t('editor_modal.unsaved_badge')}
              </span>
            )}
            <button
              onClick={() => setFullscreen((v) => !v)}
              className="p-1 rounded transition-colors"
              style={{ color: fullscreen ? 'var(--accent)' : 'var(--text-muted)' }}
              title={t(fullscreen ? 'editor_modal.exit_fullscreen' : 'editor_modal.fullscreen')}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--accent)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = fullscreen ? 'var(--accent)' : 'var(--text-muted)' }}
            >
              {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button
              autoFocus
              onClick={handleClose}
              className="p-1 rounded transition-colors"
              style={{ color: 'var(--text-muted)' }}
              title={t('editor_modal.close_esc')}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--error)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-muted)' }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Crash-recovery banner — a leftover draft can be restored or discarded */}
        {offeredDraft && (
          <div
            className="flex items-center gap-3 px-4 py-2 flex-shrink-0 text-xs"
            style={{
              backgroundColor: 'var(--warning-bg)',
              color: 'var(--warning)',
              borderBottom: '1px solid var(--border)',
            }}
            data-testid="draft-recovery-banner"
          >
            <span>
              {t('editor_modal.draft_found', {
                when: new Date(offeredDraft.savedAt).toLocaleString(),
              })}
            </span>
            <button
              onClick={handleDraftRestore}
              className="px-2 py-0.5 rounded font-medium"
              style={{
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border)',
              }}
              data-testid="draft-restore-btn"
            >
              {t('editor_modal.draft_restore')}
            </button>
            <button
              onClick={handleDraftDiscard}
              className="px-2 py-0.5 rounded font-medium"
              style={{
                backgroundColor: 'transparent',
                color: 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
              data-testid="draft-discard-btn"
            >
              {t('editor_modal.draft_discard')}
            </button>
          </div>
        )}

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

            {/* Format convert — edit mode + filePath only */}
            {filePath && (
              <div className="flex items-center gap-1 border-l pl-2 ml-1" style={{ borderColor: 'var(--border)' }}>
                <select
                  value={convertTarget}
                  onChange={(e) => setConvertTarget(e.target.value as 'ass' | 'srt' | 'vtt')}
                  className="text-[10px] py-0.5 px-1 rounded"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border)',
                    color: 'var(--text-secondary)',
                  }}
                  data-testid="convert-format-select"
                >
                  <option value="srt">SRT</option>
                  <option value="ass">ASS</option>
                  <option value="vtt">VTT</option>
                </select>
                <button
                  className="flex items-center gap-0.5 px-2 py-0.5 rounded text-[10px] font-medium"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    color: 'var(--text-secondary)',
                    border: '1px solid var(--border)',
                    opacity: convertMut.isPending ? 0.5 : 1,
                  }}
                  onClick={() =>
                    convertMut.mutate(
                      { filePath, targetFormat: convertTarget },
                      {
                        onSuccess: () => {
                          toast(t('editor_modal.converted', { format: convertTarget.toUpperCase() }))
                          void queryClient.invalidateQueries({ queryKey: ['subtitle-content', filePath] })
                        },
                        onError: () => toast(t('editor_modal.convert_failed'), 'error'),
                      },
                    )
                  }
                  disabled={convertMut.isPending}
                  data-testid="convert-format-btn"
                >
                  {convertMut.isPending && <Loader2 size={9} className="animate-spin" />}
                  {t('editor_modal.convert_button')}
                </button>
              </div>
            )}
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
                  {t('editor_modal.loading_editor')}
                </span>
              </div>
            }
          >
            {mode === 'preview' && (
              <SubtitlePreview
                filePath={filePath}
                onEdit={() => setMode('edit')}
                onClose={handleClose}
                onSeekRequest={onSeekRequest}
                className="h-full"
              />
            )}

            {mode === 'edit' && content !== null && format !== null && lastModified !== null && (
              <SubtitleEditor
                key={lastModified}
                filePath={filePath}
                initialContent={content}
                format={format}
                lastModified={lastModified}
                onSave={(newMtime) => {
                  setLastModified(newMtime)
                  // Lift the baseline to the just-saved content so the
                  // dirty-flag (derived from content !== baselineContent)
                  // clears for the WaveformEditor too.
                  setBaselineContent(content)
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
                  {t('editor_modal.loading_content')}
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
                onApplied={() => {
                  void queryClient.invalidateQueries({ queryKey: ['subtitle-content', filePath] })
                  void queryClient.invalidateQueries({ queryKey: ['subtitle-backup', filePath] })
                  setMode('preview')
                }}
              />
            )}

            {mode === 'diff' && (content === null || format === null) && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <Loader2
                  className="animate-spin h-8 w-8"
                  style={{ color: 'var(--accent)' }}
                />
                <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                  {t('editor_modal.loading_content')}
                </span>
              </div>
            )}

            {mode === 'waveform' && videoPath && filePath && (
              <WaveformEditor
                subtitlePath={filePath}
                videoPath={videoPath}
                onCueChange={handleCueTimingChange}
                selectedCueIdx={selectedCueIdx}
                onSelectAdjacentCue={handleSelectAdjacentCue}
                onSelectCue={setSelectedCueIdx}
                onCueTextChange={handleCueTextChange}
                onUndo={handleWaveformUndo}
                onRedo={handleWaveformRedo}
                canUndo={waveformUndoStack.length > 0}
                canRedo={waveformRedoStack.length > 0}
                onSave={handleWaveformSave}
                hasUnsavedChanges={hasUnsavedChanges}
                saveInFlight={saveInFlight}
                onApplyTimingFixes={handleApplyTimingFixes}
              />
            )}
          </Suspense>
        </div>
      </div>
    </div>,
    document.body
  )
}
