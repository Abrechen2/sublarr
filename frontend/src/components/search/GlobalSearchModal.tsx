/**
 * Global Ctrl+K search modal using cmdk.
 *
 * - shouldFilter={false}: filtering is done server-side via FTS5
 * - Results grouped into Series, Episodes, Subtitles sections
 * - Debounce: TanStack Query enabled only when query.length >= 2
 * - Navigation: Enter on series navigates to /library/:id, episodes to /wanted, subtitles to /history
 */
import { useState, useCallback } from 'react'
import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import { Search, Tv, Film, FileText, Loader2 } from 'lucide-react'
import { useGlobalSearch } from '@/hooks/useApi'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function GlobalSearchModal({ open, onOpenChange }: Props) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const { data, isFetching } = useGlobalSearch(query)

  // Wrap onOpenChange to reset query when dialog closes
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen) setQuery('')
    onOpenChange(nextOpen)
  }, [onOpenChange])

  const hasSeries = (data?.series?.length ?? 0) > 0
  const hasEpisodes = (data?.episodes?.length ?? 0) > 0
  const hasSubtitles = (data?.subtitles?.length ?? 0) > 0
  const hasResults = hasSeries || hasEpisodes || hasSubtitles
  const showEmpty = query.length >= 2 && !isFetching && !hasResults

  const selectAndClose = (path: string) => {
    void navigate(path)
    handleOpenChange(false)
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={handleOpenChange}
      shouldFilter={false}
      label="Global search"
      overlayClassName="fixed inset-0 bg-black/50 backdrop-blur-sm"
      contentClassName="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-background shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 border-b border-border">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <Command.Input
            value={query}
            onValueChange={setQuery}
            placeholder="Search series, episodes, subtitles..."
            className="flex-1 h-12 bg-transparent outline-none text-sm text-foreground placeholder:text-muted-foreground"
          />
          {isFetching && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />}
          <kbd className="text-xs text-muted-foreground bg-muted rounded px-1.5 py-0.5">Esc</kbd>
        </div>

        <Command.List className="max-h-80 overflow-y-auto p-2">
          {query.length < 2 && (
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              Type at least 2 characters to search...
            </Command.Empty>
          )}
          {showEmpty && (
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              No results for &quot;{query}&quot;
            </Command.Empty>
          )}

          {hasSeries && (
            <Command.Group heading="Series" className="text-xs font-semibold text-muted-foreground px-2 py-1">
              {data!.series.map((s) => (
                <Command.Item
                  key={`series-${s.id}`}
                  value={`series-${s.id}`}
                  onSelect={() => selectAndClose(`/library/series/${String(s.id)}`)}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer hover:bg-accent aria-selected:bg-accent"
                >
                  <Tv className="h-3.5 w-3.5 text-teal-500 shrink-0" />
                  <span>{s.title}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {hasEpisodes && (
            <Command.Group heading="Episodes" className="text-xs font-semibold text-muted-foreground px-2 py-1">
              {data!.episodes.map((ep) => (
                <Command.Item
                  key={`ep-${ep.id}`}
                  value={`ep-${ep.id}`}
                  onSelect={() => selectAndClose('/wanted')}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer hover:bg-accent aria-selected:bg-accent"
                >
                  <Film className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                  <span>{ep.title}</span>
                  {ep.season_episode && (
                    <span className="ml-auto text-xs text-muted-foreground">{ep.season_episode}</span>
                  )}
                </Command.Item>
              ))}
            </Command.Group>
          )}

          {hasSubtitles && (
            <Command.Group heading="Subtitles" className="text-xs font-semibold text-muted-foreground px-2 py-1">
              {data!.subtitles.map((sub) => (
                <Command.Item
                  key={`sub-${sub.id}`}
                  value={`sub-${sub.id}`}
                  onSelect={() => selectAndClose('/history')}
                  className="flex items-center gap-2 px-2 py-1.5 rounded text-sm cursor-pointer hover:bg-accent aria-selected:bg-accent"
                >
                  <FileText className="h-3.5 w-3.5 text-green-500 shrink-0" />
                  <span className="truncate max-w-xs">{sub.file_path.split('/').pop()}</span>
                  <span className="ml-auto text-xs text-muted-foreground uppercase">{sub.language}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>
      </div>
    </Command.Dialog>
  )
}
