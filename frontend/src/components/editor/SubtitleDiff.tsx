/**
 * Side-by-side diff comparison of backup vs current subtitle content.
 *
 * Uses react-codemirror-merge to render a split view with
 * syntax highlighting and built-in change visualization.
 */

import CodeMirrorMerge from 'react-codemirror-merge'
import { EditorView } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { assLanguage } from './lang-ass'
import { srtLanguage } from './lang-srt'
import { sublarrTheme } from './editor-theme'
import { useSubtitleBackup } from '@/hooks/useApi'
import { ArrowLeft, X, Loader2, AlertCircle, FileWarning } from 'lucide-react'

const Original = CodeMirrorMerge.Original
const Modified = CodeMirrorMerge.Modified

interface SubtitleDiffProps {
  filePath: string
  currentContent: string
  format: 'ass' | 'srt'
  onClose?: () => void
  onBackToEditor?: () => void
}

export function SubtitleDiff({
  filePath,
  currentContent,
  format,
  onClose,
  onBackToEditor,
}: SubtitleDiffProps) {
  const { data: backupData, isLoading, isError, error, refetch } = useSubtitleBackup(filePath)

  const language = format === 'ass' ? assLanguage : srtLanguage
  const extensions = [language, sublarrTheme, EditorView.lineWrapping]

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 items-center justify-center text-slate-400">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading backup...
        </div>
      </div>
    )
  }

  // 404: no backup found
  const axiosErr = error as { response?: { status?: number } } | null
  if (isError && axiosErr?.response?.status === 404) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-slate-400">
          <FileWarning className="h-10 w-10 text-slate-500" />
          <p className="text-sm">No backup file found. Save your changes first to create a backup.</p>
          {onBackToEditor && (
            <button
              onClick={onBackToEditor}
              className="mt-2 rounded bg-teal-600 px-4 py-1.5 text-sm text-white transition-colors hover:bg-teal-500"
            >
              Back to Editor
            </button>
          )}
        </div>
      </div>
    )
  }

  // General error state
  if (isError) {
    return (
      <div className="flex h-full flex-col">
        <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-slate-400">
          <AlertCircle className="h-10 w-10 text-red-400" />
          <p className="text-sm">Failed to load backup file</p>
          <button
            onClick={() => void refetch()}
            className="rounded bg-slate-700 px-4 py-1.5 text-sm text-slate-200 transition-colors hover:bg-slate-600"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <DiffHeader onClose={onClose} onBackToEditor={onBackToEditor} />

      {/* Column labels */}
      <div className="flex border-b border-slate-700 bg-slate-800/60 text-xs text-slate-400">
        <div className="flex-1 px-3 py-1">Original (backup)</div>
        <div className="w-px bg-slate-700" />
        <div className="flex-1 px-3 py-1">Modified (current)</div>
      </div>

      {/* Merge diff view */}
      <div className="min-h-0 flex-1 overflow-auto">
        <CodeMirrorMerge>
          <Original
            value={backupData?.content ?? ''}
            extensions={[
              ...extensions,
              EditorState.readOnly.of(true),
            ]}
          />
          <Modified
            value={currentContent}
            extensions={[
              ...extensions,
              EditorState.readOnly.of(true),
            ]}
          />
        </CodeMirrorMerge>
      </div>
    </div>
  )
}

/** Shared header bar for all diff states */
function DiffHeader({
  onClose,
  onBackToEditor,
}: {
  onClose?: () => void
  onBackToEditor?: () => void
}) {
  return (
    <div className="flex items-center gap-2 border-b border-slate-700 bg-slate-800/80 px-3 py-1.5">
      <span className="text-sm font-medium text-slate-200">Diff View</span>

      <div className="flex-1" />

      {onBackToEditor && (
        <button
          onClick={onBackToEditor}
          className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm
            text-slate-300 transition-colors hover:bg-slate-700"
          title="Back to editor"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Editor
        </button>
      )}

      {onClose && (
        <button
          onClick={onClose}
          className="rounded p-1.5 text-slate-400 transition-colors hover:bg-slate-700 hover:text-slate-200"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
