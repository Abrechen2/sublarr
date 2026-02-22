/**
 * SubtitlePreview -- read-only subtitle viewer with syntax highlighting.
 *
 * Renders full file content in a CodeMirror instance with ASS or SRT
 * syntax highlighting. Integrates SubtitleTimeline for visual cue navigation.
 * Clicking a timeline cue scrolls the editor to the approximate line.
 */

import { useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import CodeMirror from '@uiw/react-codemirror'
import { EditorView } from '@codemirror/view'
import type { ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { Loader2, Pencil, X, AlertCircle, RefreshCw } from 'lucide-react'
import { useSubtitleContent, useSubtitleParse } from '@/hooks/useApi'
import { assLanguage } from '@/components/editor/lang-ass'
import { srtLanguage } from '@/components/editor/lang-srt'
import { sublarrTheme } from '@/components/editor/editor-theme'
import SubtitleTimeline from '@/components/editor/SubtitleTimeline'

interface SubtitlePreviewProps {
  filePath: string
  onEdit?: () => void           // Optional callback to switch to edit mode
  onClose?: () => void          // Close preview
  className?: string
}

/** Format bytes to human-readable size. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function SubtitlePreview({
  filePath,
  onEdit,
  onClose,
  className = '',
}: SubtitlePreviewProps) {
  const { t } = useTranslation('editor')
  const editorRef = useRef<ReactCodeMirrorRef>(null)

  const {
    data: contentData,
    isLoading: contentLoading,
    isError: contentError,
    error: contentErrorObj,
    refetch: refetchContent,
  } = useSubtitleContent(filePath)

  const {
    data: parseData,
  } = useSubtitleParse(filePath)

  // Select the correct language extension based on format
  const languageExt = contentData?.format === 'srt' ? srtLanguage : assLanguage

  // Handle timeline cue click: scroll editor to approximate line
  const handleCueClick = useCallback((cueIndex: number) => {
    const view = editorRef.current?.view
    if (!view || !contentData) return

    // Estimate line position based on format and cue index
    let targetLine: number
    if (contentData.format === 'ass') {
      // ASS files have header sections (~30-50 lines) before events
      // Each dialogue line is a single line in the events section
      const headerEstimate = Math.min(Math.floor(contentData.total_lines * 0.15), 60)
      targetLine = headerEstimate + cueIndex + 1
    } else {
      // SRT files: each cue is ~3-4 lines (number, timestamp, text, blank)
      targetLine = cueIndex * 4 + 1
    }

    // Clamp to valid line range
    targetLine = Math.min(targetLine, view.state.doc.lines)
    targetLine = Math.max(targetLine, 1)

    const line = view.state.doc.line(targetLine)
    view.dispatch({
      effects: EditorView.scrollIntoView(line.from, { y: 'center' }),
    })
  }, [contentData])

  // Loading state
  if (contentLoading) {
    return (
      <div className={`flex items-center justify-center p-12 ${className}`}>
        <Loader2 className="w-6 h-6 animate-spin text-teal-400 mr-2" />
        <span className="text-muted">{t('loading', 'Loading subtitle...')}</span>
      </div>
    )
  }

  // Error state
  if (contentError) {
    const httpStatus = (contentErrorObj as { response?: { status?: number } })?.response?.status
    const errorMessage = httpStatus === 403
      ? t('error403', 'File not accessible: path is outside the configured media directory')
      : httpStatus === 404
        ? t('error404', 'Subtitle file not found')
        : (contentErrorObj as Error)?.message || t('loadError', 'Failed to load subtitle file')

    return (
      <div className={`flex flex-col items-center justify-center p-12 gap-3 ${className}`}>
        <AlertCircle className="w-8 h-8 text-red-400" />
        <p className="text-red-400 text-sm">{errorMessage}</p>
        {httpStatus !== 403 && httpStatus !== 404 && (
          <button
            onClick={() => refetchContent()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-elevated hover:bg-hover text-foreground transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            {t('retry', 'Retry')}
          </button>
        )}
      </div>
    )
  }

  if (!contentData) return null

  return (
    <div className={`flex flex-col ${className}`}>
      {/* Metadata bar */}
      <div className="flex items-center gap-3 px-3 py-2 bg-elevated border-b border-border text-sm">
        {/* Format badge */}
        <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-teal-500/20 text-teal-400 uppercase">
          {contentData.format}
        </span>

        <span className="text-muted">{contentData.encoding}</span>
        <span className="text-muted">{contentData.total_lines.toLocaleString()} {t('lines', 'lines')}</span>
        <span className="text-muted">{formatBytes(contentData.size_bytes)}</span>

        {/* Quality score summary badge */}
        {parseData?.has_quality_scores && (() => {
          const scores = parseData.cues
            .map((c) => c.quality_score)
            .filter((s): s is number => s !== undefined)
          if (scores.length === 0) return null
          const avg = Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
          const low = scores.filter((s) => s < 50).length
          const color = avg >= 75
            ? { bg: 'rgba(16,185,129,0.12)', text: 'rgb(16 185 129)' }
            : avg >= 50
              ? { bg: 'rgba(245,158,11,0.12)', text: 'rgb(245 158 11)' }
              : { bg: 'rgba(239,68,68,0.12)', text: 'rgb(239 68 68)' }
          return (
            <span
              className="px-2 py-0.5 rounded text-xs font-medium"
              style={{ backgroundColor: color.bg, color: color.text }}
              title={`Average translation quality: ${avg}%${low > 0 ? `, ${low} low-quality line${low > 1 ? 's' : ''}` : ''}`}
            >
              Q: {avg}%{low > 0 ? ` · ${low} low` : ''}
            </span>
          )
        })()}

        <div className="flex-1" />

        {/* Edit button */}
        {onEdit && (
          <button
            onClick={onEdit}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded bg-teal-500/10 hover:bg-teal-500/20 text-teal-400 transition-colors"
            title={t('edit', 'Edit')}
          >
            <Pencil className="w-3.5 h-3.5" />
            {t('edit', 'Edit')}
          </button>
        )}

        {/* Close button */}
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-hover text-muted hover:text-foreground transition-colors"
            title={t('close', 'Close')}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Timeline */}
      {parseData && parseData.cues.length > 0 && (
        <div className="px-3 py-2 bg-elevated border-b border-border">
          <SubtitleTimeline
            cues={parseData.cues}
            totalDuration={parseData.total_duration}
            onCueClick={handleCueClick}
            styles={parseData.styles}
          />
        </div>
      )}

      {/* CodeMirror read-only view */}
      <div className="flex-1 overflow-auto">
        <CodeMirror
          ref={editorRef}
          value={contentData.content}
          editable={false}
          readOnly={true}
          extensions={[languageExt]}
          theme={sublarrTheme}
          basicSetup={{
            lineNumbers: true,
            foldGutter: false,
            highlightActiveLine: false,
          }}
        />
      </div>
    </div>
  )
}
