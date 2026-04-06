import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSubtitleTool, usePreviewSubtitle } from '@/hooks/useApi'
import { Loader2, AlertTriangle, Wrench, Eye } from 'lucide-react'
import { toast } from '@/components/shared/Toast'

// ─── Subtitle Tools Tab ──────────────────────────────────────────────────────

function highlightLine(line: string, format: string): string {
  if (format === 'ass') {
    if (line.startsWith('[') || line.startsWith('Format:') || line.startsWith('Style:')) return 'var(--accent)'
    if (line.startsWith('Dialogue:') || line.startsWith('Comment:')) return 'var(--text-primary)'
    return 'var(--text-muted)'
  }
  // SRT
  if (/^\d+$/.test(line.trim())) return 'var(--accent)'
  if (/-->/.test(line)) return 'var(--text-muted)'
  return 'var(--text-primary)'
}

export function SubtitleToolsTab() {
  const { t } = useTranslation('settings')
  const subtitleTool = useSubtitleTool()
  const previewMutation = usePreviewSubtitle()
  const [hiPath, setHiPath] = useState('')
  const [timingPath, setTimingPath] = useState('')
  const [timingOffset, setTimingOffset] = useState(0)
  const [fixesPath, setFixesPath] = useState('')
  const [fixes, setFixes] = useState({ encoding: true, whitespace: true, linebreaks: true, empty_lines: true })
  const [previewPath, setPreviewPath] = useState('')
  const [previewData, setPreviewData] = useState<{ format: string; lines: string[]; total_lines: number } | null>(null)
  const [toolResult, setToolResult] = useState<Record<string, string | null>>({})

  const runTool = (tool: string, params: Record<string, unknown>, resultKey: string) => {
    subtitleTool.mutate({ tool, params }, {
      onSuccess: (data) => {
        setToolResult((prev) => ({ ...prev, [resultKey]: data.status || 'Done' }))
        toast(`Tool "${tool}" completed successfully`)
      },
      onError: () => {
        setToolResult((prev) => ({ ...prev, [resultKey]: 'Failed' }))
        toast(`Tool "${tool}" failed`, 'error')
      },
    })
  }

  const handlePreview = () => {
    if (!previewPath.trim()) return
    previewMutation.mutate(previewPath, {
      onSuccess: (data) => setPreviewData(data),
      onError: () => toast('Preview failed', 'error'),
    })
  }

  return (
    <div className="space-y-4">
      <div className="text-xs px-1" style={{ color: 'var(--text-muted)' }}>
        <AlertTriangle size={12} className="inline mr-1" />
        A backup (.bak) is created before any modification.
      </div>

      {/* Remove HI Markers */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Remove Hearing-Impaired Markers
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Removes [HI], (music), and other hearing-impaired annotations from subtitle files.
        </p>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={hiPath}
            onChange={(e) => setHiPath(e.target.value)}
            placeholder="File path (e.g. /media/show/sub.srt)"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{
              backgroundColor: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '13px',
            }}
          />
          <button
            onClick={() => runTool('remove-hi', { file_path: hiPath }, 'hi')}
            disabled={!hiPath.trim() || subtitleTool.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !hiPath.trim() ? 0.5 : 1 }}
          >
            {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
            Remove
          </button>
        </div>
        {toolResult.hi && (
          <p className="text-xs mt-2" style={{ color: toolResult.hi === 'Failed' ? 'var(--error)' : 'var(--success)' }}>
            Result: {toolResult.hi}
          </p>
        )}
      </div>

      {/* Adjust Timing */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Adjust Timing
        </h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Shift all subtitle timestamps by a specified millisecond offset.
          Positive values delay, negative values advance.
        </p>
        <div className="flex items-center gap-2">
          <input type="text" value={timingPath} onChange={(e) => setTimingPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
          <div className="flex items-center gap-1">
            <input type="number" value={timingOffset} onChange={(e) => setTimingOffset(parseInt(e.target.value) || 0)}
              className="w-24 px-2 py-2 rounded-md text-sm text-center"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
            <span className="text-xs shrink-0" style={{ color: 'var(--text-muted)' }}>ms ({timingOffset >= 0 ? 'delay' : 'advance'})</span>
          </div>
          <button
            onClick={() => runTool('adjust-timing', { file_path: timingPath, offset_ms: timingOffset }, 'timing')}
            disabled={!timingPath.trim() || subtitleTool.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !timingPath.trim() ? 0.5 : 1 }}
          >
            {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
            Apply
          </button>
        </div>
        {toolResult.timing && (
          <p className="text-xs mt-2" style={{ color: toolResult.timing === 'Failed' ? 'var(--error)' : 'var(--success)' }}>Result: {toolResult.timing}</p>
        )}
      </div>

      {/* Common Fixes */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{t('subtitle_tools_tab.common_fixes')}</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
          Apply common subtitle cleaning operations: fix encoding, trim whitespace, normalize line breaks, remove empty lines.
        </p>
        <div className="flex items-center gap-2 mb-3">
          <input type="text" value={fixesPath} onChange={(e) => setFixesPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
        </div>
        <div className="flex flex-wrap gap-3 mb-3">
          {(['encoding', 'whitespace', 'linebreaks', 'empty_lines'] as const).map((fix) => (
            <label key={fix} className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={fixes[fix]} onChange={(e) => setFixes((prev) => ({ ...prev, [fix]: e.target.checked }))}
                className="rounded" style={{ accentColor: 'var(--accent)' }} />
              {fix.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
            </label>
          ))}
        </div>
        <button
          onClick={() => runTool('common-fixes', { file_path: fixesPath, fixes }, 'fixes')}
          disabled={!fixesPath.trim() || subtitleTool.isPending}
          className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white"
          style={{ backgroundColor: 'var(--accent)', opacity: !fixesPath.trim() ? 0.5 : 1 }}
        >
          {subtitleTool.isPending ? <Loader2 size={14} className="animate-spin" /> : <Wrench size={14} />}
          Apply Fixes
        </button>
        {toolResult.fixes && (
          <p className="text-xs mt-2" style={{ color: toolResult.fixes === 'Failed' ? 'var(--error)' : 'var(--success)' }}>Result: {toolResult.fixes}</p>
        )}
      </div>

      {/* Preview */}
      <div className="rounded-lg p-5" style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
        <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>{t('subtitle_tools_tab.preview_subtitle')}</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--text-muted)' }}>View the first 100 lines of a subtitle file.</p>
        <div className="flex items-center gap-2 mb-3">
          <input type="text" value={previewPath} onChange={(e) => setPreviewPath(e.target.value)} placeholder="File path"
            className="flex-1 px-3 py-2 rounded-md text-sm"
            style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px' }} />
          <button
            onClick={handlePreview}
            disabled={!previewPath.trim() || previewMutation.isPending}
            className="flex items-center gap-1 px-3 py-2 rounded-md text-sm font-medium text-white shrink-0"
            style={{ backgroundColor: 'var(--accent)', opacity: !previewPath.trim() ? 0.5 : 1 }}
          >
            {previewMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Eye size={14} />}
            Preview
          </button>
        </div>
        {previewData && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ backgroundColor: 'var(--accent-bg)', color: 'var(--accent)' }}>
                {previewData.format.toUpperCase()}
              </span>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{previewData.total_lines} total lines</span>
            </div>
            <div
              className="max-h-64 overflow-auto rounded p-3 text-xs"
              style={{ backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', lineHeight: 1.6 }}
            >
              {previewData.lines.map((line, i) => (
                <div key={i} style={{ color: highlightLine(line, previewData.format) }}>{line || '\u00A0'}</div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
