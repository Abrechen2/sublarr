/**
 * Full-featured CodeMirror subtitle editor with toolbar, validation, and save.
 *
 * Features:
 * - ASS/SRT syntax highlighting via custom tokenizers
 * - Undo/redo (CodeMirror history extension)
 * - Find & replace (CodeMirror search extension, Ctrl+H)
 * - Debounced validation (500ms after change)
 * - Save with backup + mtime conflict detection (Ctrl+S)
 * - Toolbar buttons and keyboard shortcuts
 * - Unsaved changes guard (beforeunload)
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { keymap } from '@codemirror/view'
import { EditorView } from '@codemirror/view'
import { history, undo, redo, historyKeymap } from '@codemirror/commands'
import { search, searchKeymap, openSearchPanel } from '@codemirror/search'
import { defaultKeymap } from '@codemirror/commands'
import { assLanguage } from './lang-ass'
import { srtLanguage } from './lang-srt'
import { sublarrTheme } from './editor-theme'
import { useSaveSubtitle, useValidateSubtitle } from '@/hooks/useApi'
import { toast } from '@/components/shared/Toast'
import type { SubtitleValidation } from '@/api/client'
import {
  Save, CheckCircle, Search, Undo2, Redo2,
  GitCompare, X, AlertTriangle, Loader2,
} from 'lucide-react'

interface SubtitleEditorProps {
  filePath: string
  initialContent: string
  format: 'ass' | 'srt'
  lastModified: number
  onSave?: (newMtime: number) => void
  onClose?: () => void
  onDiffView?: () => void
}

export function SubtitleEditor({
  filePath,
  initialContent,
  format,
  lastModified,
  onSave,
  onClose,
  onDiffView,
}: SubtitleEditorProps) {
  const [content, setContent] = useState(initialContent)
  const [hasChanges, setHasChanges] = useState(false)
  const [validationResult, setValidationResult] = useState<SubtitleValidation | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isValidating, setIsValidating] = useState(false)
  const [currentMtime, setCurrentMtime] = useState(lastModified)

  const editorRef = useRef<ReactCodeMirrorRef>(null)
  const lastValidatedContent = useRef<string>('')
  const validationTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const saveMutation = useSaveSubtitle()
  const validateMutation = useValidateSubtitle()

  // Language extension based on format
  const languageExtension = useMemo(
    () => (format === 'ass' ? assLanguage : srtLanguage),
    [format],
  )

  // Save handler
  const handleSave = useCallback(async () => {
    if (!hasChanges || isSaving) return

    setIsSaving(true)
    try {
      const result = await saveMutation.mutateAsync({
        filePath,
        content,
        lastModified: currentMtime,
      })
      setCurrentMtime(result.new_mtime)
      setHasChanges(false)
      onSave?.(result.new_mtime)
      toast('File saved successfully', 'success')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr.response?.status === 409) {
        toast('Conflict: file was modified externally. Reload before saving.', 'error')
      } else {
        toast('Failed to save file', 'error')
      }
    } finally {
      setIsSaving(false)
    }
  }, [hasChanges, isSaving, content, filePath, currentMtime, saveMutation, onSave])

  // Validate handler
  const runValidation = useCallback(async (text: string) => {
    if (text === lastValidatedContent.current) return

    setIsValidating(true)
    try {
      const result = await validateMutation.mutateAsync({
        content: text,
        format,
      })
      setValidationResult(result)
      lastValidatedContent.current = text
    } catch {
      setValidationResult({
        valid: false,
        error: 'Validation request failed',
        warnings: [],
      })
    } finally {
      setIsValidating(false)
    }
  }, [validateMutation, format])

  // Debounced validation on content change
  useEffect(() => {
    if (!hasChanges && content === initialContent) return

    if (validationTimer.current) {
      clearTimeout(validationTimer.current)
    }

    validationTimer.current = setTimeout(() => {
      void runValidation(content)
    }, 500)

    return () => {
      if (validationTimer.current) {
        clearTimeout(validationTimer.current)
      }
    }
  }, [content, hasChanges, initialContent, runValidation])

  // Unsaved changes guard
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (hasChanges) {
        e.preventDefault()
      }
    }

    if (hasChanges) {
      window.addEventListener('beforeunload', handler)
    }

    return () => {
      window.removeEventListener('beforeunload', handler)
    }
  }, [hasChanges])

  // Custom keymap for Ctrl+S
  const saveKeymap = useMemo(
    () =>
      keymap.of([
        {
          key: 'Mod-s',
          run: () => {
            void handleSave()
            return true
          },
        },
      ]),
    [handleSave],
  )

  // All extensions
  const extensions = useMemo(
    () => [
      languageExtension,
      history(),
      search(),
      keymap.of([...defaultKeymap, ...historyKeymap, ...searchKeymap]),
      saveKeymap,
      EditorView.lineWrapping,
    ],
    [languageExtension, saveKeymap],
  )

  // Editor change handler
  const handleChange = useCallback(
    (value: string) => {
      setContent(value)
      setHasChanges(value !== initialContent)
    },
    [initialContent],
  )

  // Toolbar button handlers
  const handleUndo = useCallback(() => {
    const view = editorRef.current?.view
    if (view) undo(view)
  }, [])

  const handleRedo = useCallback(() => {
    const view = editorRef.current?.view
    if (view) redo(view)
  }, [])

  const handleFindReplace = useCallback(() => {
    const view = editorRef.current?.view
    if (view) openSearchPanel(view)
  }, [])

  const handleClose = useCallback(() => {
    if (hasChanges) {
      if (window.confirm('You have unsaved changes. Close anyway?')) {
        onClose?.()
      }
    } else {
      onClose?.()
    }
  }, [hasChanges, onClose])

  const handleValidateClick = useCallback(() => {
    void runValidation(content)
  }, [content, runValidation])

  // Line and character counts
  const lineCount = content.split('\n').length
  const charCount = content.length

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-1 border-b border-slate-700 bg-slate-800/80 px-3 py-1.5">
        {/* Save */}
        <button
          onClick={() => void handleSave()}
          disabled={!hasChanges || isSaving}
          className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm font-medium
            text-teal-400 transition-colors hover:bg-slate-700
            disabled:cursor-not-allowed disabled:text-slate-500 disabled:hover:bg-transparent"
          title="Save (Ctrl+S)"
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save
        </button>

        <div className="mx-1 h-5 w-px bg-slate-700" />

        {/* Validate */}
        <button
          onClick={handleValidateClick}
          disabled={isValidating}
          className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm
            text-slate-300 transition-colors hover:bg-slate-700
            disabled:cursor-not-allowed disabled:text-slate-500"
          title="Validate subtitle structure"
        >
          {isValidating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CheckCircle className="h-4 w-4" />
          )}
          Validate
        </button>

        {/* Validation badge */}
        {validationResult && (
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              validationResult.valid
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-red-500/20 text-red-400'
            }`}
          >
            {validationResult.valid
              ? `Valid (${validationResult.event_count ?? 0} events${
                  validationResult.style_count
                    ? `, ${validationResult.style_count} styles`
                    : ''
                })`
              : `Invalid: ${validationResult.error ?? 'unknown error'}`}
          </span>
        )}

        <div className="mx-1 h-5 w-px bg-slate-700" />

        {/* Find & Replace */}
        <button
          onClick={handleFindReplace}
          className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm
            text-slate-300 transition-colors hover:bg-slate-700"
          title="Find & Replace (Ctrl+H)"
        >
          <Search className="h-4 w-4" />
          Find
        </button>

        {/* Undo / Redo */}
        <button
          onClick={handleUndo}
          className="rounded p-1.5 text-slate-300 transition-colors hover:bg-slate-700"
          title="Undo (Ctrl+Z)"
        >
          <Undo2 className="h-4 w-4" />
        </button>
        <button
          onClick={handleRedo}
          className="rounded p-1.5 text-slate-300 transition-colors hover:bg-slate-700"
          title="Redo (Ctrl+Y)"
        >
          <Redo2 className="h-4 w-4" />
        </button>

        <div className="flex-1" />

        {/* Diff View */}
        {onDiffView && (
          <button
            onClick={onDiffView}
            className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm
              text-slate-300 transition-colors hover:bg-slate-700"
            title="Compare with backup"
          >
            <GitCompare className="h-4 w-4" />
            Diff
          </button>
        )}

        {/* Close */}
        {onClose && (
          <button
            onClick={handleClose}
            className="rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
            title="Close editor"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Editor */}
      <div className="min-h-0 flex-1">
        <CodeMirror
          ref={editorRef}
          value={initialContent}
          onChange={handleChange}
          extensions={extensions}
          theme={sublarrTheme}
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            highlightActiveLine: true,
            bracketMatching: false,
            autocompletion: false,
          }}
          className="h-full [&_.cm-editor]:h-full"
        />
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 border-t border-slate-700 bg-slate-800/80 px-3 py-1">
        {/* Format badge */}
        <span className="rounded bg-slate-700 px-1.5 py-0.5 text-xs font-medium uppercase text-slate-300">
          {format}
        </span>

        {/* Line / char counts */}
        <span className="text-xs text-slate-500">
          {lineCount} lines, {charCount.toLocaleString()} chars
        </span>

        {/* Validation status */}
        {isValidating && (
          <span className="flex items-center gap-1 text-xs text-slate-500">
            <Loader2 className="h-3 w-3 animate-spin" />
            Validating...
          </span>
        )}
        {!isValidating && validationResult && (
          <span
            className={`text-xs ${
              validationResult.valid ? 'text-emerald-400' : 'text-red-400'
            }`}
          >
            {validationResult.valid ? 'Valid' : 'Invalid'}
          </span>
        )}

        <div className="flex-1" />

        {/* Unsaved changes indicator */}
        {hasChanges && (
          <span className="flex items-center gap-1 text-xs text-amber-400">
            <AlertTriangle className="h-3 w-3" />
            Unsaved changes
          </span>
        )}
      </div>
    </div>
  )
}
