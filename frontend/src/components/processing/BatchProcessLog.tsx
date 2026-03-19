import { CheckCircle, XCircle, RotateCcw } from 'lucide-react'
import { undoProcessSubtitle } from '@/api/client'
import { toast } from '@/components/shared/Toast'

interface LogEntry {
  filename: string
  status: 'ok' | 'failed' | 'skipped'
  changes: number
  backed_up: boolean
  sub_path: string
}

interface Props {
  entries: LogEntry[]
  current: number
  total: number
}

export function BatchProcessLog({ entries, current, total }: Props) {
  async function handleUndo(path: string) {
    try {
      await undoProcessSubtitle(path)
      toast('Backup wiederhergestellt', 'success')
    } catch {
      toast('Wiederherstellen fehlgeschlagen', 'error')
    }
  }

  const pct = total > 0 ? Math.round((current / total) * 100) : 0

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-zinc-700 rounded-full h-2">
          <div className="bg-blue-500 h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
        </div>
        <span className="text-xs text-zinc-400 whitespace-nowrap">{current} / {total}</span>
      </div>

      <div className="max-h-80 overflow-y-auto space-y-0.5">
        {entries.map((e, i) => (
          <div key={i} className="flex items-center gap-2 px-2 py-1 rounded text-xs hover:bg-zinc-800">
            {e.status === 'ok'
              ? <CheckCircle size={12} className="text-green-400 shrink-0" />
              : <XCircle size={12} className="text-red-400 shrink-0" />}
            <span className="flex-1 truncate text-zinc-300">{e.filename}</span>
            {e.status === 'ok' && e.changes > 0 && (
              <span className="text-zinc-500">{e.changes} Änderungen</span>
            )}
            {e.backed_up && (
              <button
                onClick={() => handleUndo(e.sub_path)}
                className="flex items-center gap-1 text-yellow-400 hover:text-yellow-300"
              >
                <RotateCcw size={10} /> Undo
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
