/**
 * Single read-only CodeMirror panel for subtitle comparison.
 *
 * Displays syntax-highlighted subtitle content with a label header.
 * Supports ASS and SRT formats via the existing editor language modules.
 */

import { useRef, useCallback, useMemo } from 'react'
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { EditorView } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { assLanguage } from '@/components/editor/lang-ass'
import { srtLanguage } from '@/components/editor/lang-srt'
import { sublarrTheme } from '@/components/editor/editor-theme'

interface ComparisonPanelProps {
  label: string
  content: string
  format: 'ass' | 'srt'
  onScroll?: (lineNumber: number) => void
}

export function ComparisonPanel({ label, content, format, onScroll }: ComparisonPanelProps) {
  const editorRef = useRef<ReactCodeMirrorRef>(null)

  const language = format === 'ass' ? assLanguage : srtLanguage

  const handleScroll = useCallback(() => {
    if (!onScroll || !editorRef.current?.view) return
    const view = editorRef.current.view
    const rect = view.dom.getBoundingClientRect()
    const topPos = view.posAtCoords({ x: rect.left + 10, y: rect.top + 10 })
    if (topPos !== null) {
      const line = view.state.doc.lineAt(topPos).number
      onScroll(line)
    }
  }, [onScroll])

  const scrollHandler = useMemo(() => {
    return EditorView.domEventHandlers({
      scroll: () => {
        handleScroll()
        return false
      },
    })
  }, [handleScroll])

  const extensions = useMemo(
    () => [
      language,
      sublarrTheme,
      EditorState.readOnly.of(true),
      EditorView.lineWrapping,
      scrollHandler,
    ],
    [language, scrollHandler]
  )

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden rounded-lg"
      style={{ border: '1px solid var(--border)' }}
    >
      {/* Label header */}
      <div
        className="flex items-center px-3 py-1.5 text-xs font-medium shrink-0"
        style={{
          backgroundColor: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border)',
          color: 'var(--text-secondary)',
        }}
      >
        <span className="truncate">{label}</span>
        <span
          className="ml-auto text-[10px] uppercase font-bold px-1.5 py-0.5 rounded"
          style={{
            backgroundColor: format === 'ass' ? 'rgba(16,185,129,0.1)' : 'var(--bg-surface)',
            color: format === 'ass' ? 'var(--success)' : 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {format}
        </span>
      </div>

      {/* CodeMirror editor */}
      <div className="flex-1 min-h-0 overflow-auto">
        <CodeMirror
          ref={editorRef}
          value={content}
          extensions={extensions}
          basicSetup={{
            lineNumbers: true,
            foldGutter: false,
            highlightActiveLine: false,
          }}
          editable={false}
        />
      </div>
    </div>
  )
}
