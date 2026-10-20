/**
 * Saved subtitles of another episode (e.g. season 1's twelfth on S02E12).
 *
 * Downloads from before the episode gate are never revisited by a search, so
 * this lists those whose winning release names another episode and can send
 * them back: blocked for that video only, kept until a replacement is saved,
 * searched again. Listing is free; nothing is downloaded until the search runs.
 */
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { RotateCcw, SearchX } from 'lucide-react';
import { requeueWrongEpisodes, scanWrongEpisodes } from '@/api/system/repair';

const SHOWN = 50;

export function WrongEpisodePanel({ language }: { language: string }) {
  const { t } = useTranslation('common');

  const {
    data: scan,
    isFetching: scanning,
    refetch,
  } = useQuery({
    queryKey: ['repair-wrong-episodes', language],
    queryFn: () => scanWrongEpisodes(language || undefined),
    enabled: false,
  });

  const requeue = useMutation({
    mutationFn: () => requeueWrongEpisodes(language || undefined),
  });
  const resetRequeue = requeue.reset;

  // The done state belongs to the scan it acted on: another language, or a
  // new scan, can be requeued again (VM 191: the button stayed disabled).
  useEffect(() => {
    resetRequeue();
  }, [language, resetRequeue]);

  const rescan = () => {
    resetRequeue();
    void refetch();
  };

  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div className="flex items-start gap-2">
        <SearchX size={16} className="mt-0.5 shrink-0 text-warning" />
        <div>
          <h3 className="text-sm font-semibold text-primary">{t('repair.wrong_episode.title')}</h3>
          <p className="text-xs text-muted mt-1">{t('repair.wrong_episode.intro')}</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={rescan}
          disabled={scanning}
          className="rounded px-3 py-1.5 text-xs font-medium border border-border disabled:opacity-50"
        >
          {scanning ? t('repair.scanning') : t('repair.wrong_episode.scan')}
        </button>
        <button
          onClick={() => requeue.mutate()}
          disabled={!scan?.count || requeue.isPending || requeue.isSuccess}
          className="flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <RotateCcw size={13} />
          {t('repair.wrong_episode.requeue', { count: scan?.count ?? 0 })}
        </button>
      </div>

      {requeue.isSuccess && (
        <p className="text-[11px] text-success">{t('repair.wrong_episode.requeued')}</p>
      )}
      {requeue.isError && (
        <p className="text-[11px] text-danger">{t('repair.wrong_episode.requeue_failed')}</p>
      )}

      {scan && (
        <div className="rounded-md border border-border bg-page p-3 text-xs space-y-1.5">
          {scan.count === 0 ? (
            <p className="text-muted">{t('repair.wrong_episode.none')}</p>
          ) : (
            <>
              <p className="text-muted">{t('repair.wrong_episode.found', { count: scan.count })}</p>
              <ul className="space-y-1 max-h-64 overflow-y-auto">
                {scan.findings.slice(0, SHOWN).map(f => (
                  <li key={f.sidecar} className="break-all">
                    <span className="text-primary">{f.sidecar.split('/').pop()}</span>
                    <span className="text-muted">
                      {' '}
                      — {f.provider}: {f.release}
                    </span>
                  </li>
                ))}
              </ul>
              {scan.count > SHOWN && (
                <p className="text-[11px] text-muted">
                  {t('repair.wrong_episode.more', { count: scan.count - SHOWN })}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
