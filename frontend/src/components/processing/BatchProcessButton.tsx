import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Play } from 'lucide-react'
import { processLibraryAll } from '@/api/client'
import { toast } from '@/components/shared/Toast'

export function BatchProcessButton() {
  const { t } = useTranslation('common')
  const [open, setOpen] = useState(false)

  async function start(filter: 'all' | 'unprocessed') {
    setOpen(false)
    try {
      await processLibraryAll(filter)
      toast(t('batch_process.started'), 'success')
    } catch {
      toast(t('batch_process.start_failed'), 'error')
    }
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 px-3 py-1.5 text-sm bg-zinc-700 hover:bg-zinc-600 rounded border border-zinc-600"
      >
        <Play size={14} /> {t('batch_process.process_library')} <ChevronDown size={12} />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-52 bg-zinc-900 border border-zinc-700 rounded shadow-lg z-10">
          <button onClick={() => start('all')} className="w-full px-3 py-2 text-sm text-left hover:bg-zinc-800">
            {t('batch_process.all_series')}
          </button>
          <button onClick={() => start('unprocessed')} className="w-full px-3 py-2 text-sm text-left hover:bg-zinc-800">
            {t('batch_process.unprocessed')}
          </button>
        </div>
      )}
    </div>
  )
}
