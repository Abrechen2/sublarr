import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WrongEpisodePanel } from '../WrongEpisodePanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: { count?: number }) => (o?.count !== undefined ? `${k}:${o.count}` : k),
  }),
}));

const mockScan = vi.fn();
const mockRequeue = vi.fn();
vi.mock('@/api/system/repair', () => ({
  scanWrongEpisodes: (language?: string) => mockScan(language),
  requeueWrongEpisodes: (language?: string) => mockRequeue(language),
}));

const finding = {
  video: '/tv/Clevatess/Season 2/Clevatess - S02E12.mkv',
  sidecar: '/tv/Clevatess/Season 2/Clevatess - S02E12.de.srt',
  language: 'de',
  provider: 'opensubtitles',
  subtitle_id: '11975292',
  release: 'Clevatess - S01E12 [CR WEB-DL 1080p]',
  reason: 'names S01E12, query is S02E12',
};

function renderPanel(language = 'de') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const panel = (lang: string) => (
    <QueryClientProvider client={qc}>
      <WrongEpisodePanel language={lang} />
    </QueryClientProvider>
  );
  const view = render(panel(language));
  return { ...view, switchTo: (lang: string) => view.rerender(panel(lang)) };
}

describe('WrongEpisodePanel', () => {
  beforeEach(() => {
    mockScan.mockReset();
    mockRequeue.mockReset();
  });

  it('scans only on demand and lists what it found', async () => {
    mockScan.mockResolvedValue({ count: 1, findings: [finding] });
    renderPanel();
    expect(mockScan).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));

    expect(await screen.findByText('Clevatess - S02E12.de.srt')).toBeTruthy();
    expect(screen.getByText(/Clevatess - S01E12 \[CR WEB-DL 1080p\]/)).toBeTruthy();
    expect(mockScan).toHaveBeenCalledWith('de');
  });

  it('requeues for the selected language once, then stays disabled', async () => {
    mockScan.mockResolvedValue({ count: 1, findings: [finding] });
    mockRequeue.mockResolvedValue(undefined);
    renderPanel();
    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));
    const button = await screen.findByText('repair.wrong_episode.requeue:1');

    fireEvent.click(button);

    await screen.findByText('repair.wrong_episode.requeued');
    expect(mockRequeue).toHaveBeenCalledWith('de');
    expect(button.closest('button')?.disabled).toBe(true);
  });

  it('cannot requeue before a scan found anything', async () => {
    mockScan.mockResolvedValue({ count: 0, findings: [] });
    renderPanel();
    expect(screen.getByText('repair.wrong_episode.requeue:0').closest('button')?.disabled).toBe(
      true
    );
    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));
    await screen.findByText('repair.wrong_episode.none');
    await waitFor(() => expect(mockRequeue).not.toHaveBeenCalled());
  });

  it('can requeue another language after the first one is done', async () => {
    // VM 191 (RC 1.17.0-rc.1): the done state outlived the language switch,
    // so the second language's findings could never be requeued.
    mockScan.mockImplementation(async (language: string) => ({
      count: 1,
      findings: [{ ...finding, language, sidecar: `/tv/Clevatess - S02E12.${language}.srt` }],
    }));
    mockRequeue.mockResolvedValue(undefined);
    const { switchTo } = renderPanel('de');
    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));
    fireEvent.click(await screen.findByText('repair.wrong_episode.requeue:1'));
    await screen.findByText('repair.wrong_episode.requeued');

    switchTo('en');
    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));
    await screen.findByText('Clevatess - S02E12.en.srt');
    const button = screen.getByText('repair.wrong_episode.requeue:1').closest('button');
    await waitFor(() => expect(button?.disabled).toBe(false));
    expect(screen.queryByText('repair.wrong_episode.requeued')).toBeNull();

    fireEvent.click(button!);
    await waitFor(() => expect(mockRequeue).toHaveBeenLastCalledWith('en'));
  });

  it('a new scan of the same language can be requeued again', async () => {
    mockScan.mockResolvedValue({ count: 1, findings: [finding] });
    mockRequeue.mockResolvedValue(undefined);
    renderPanel();
    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));
    fireEvent.click(await screen.findByText('repair.wrong_episode.requeue:1'));
    await screen.findByText('repair.wrong_episode.requeued');

    fireEvent.click(screen.getByText('repair.wrong_episode.scan'));

    const button = screen.getByText('repair.wrong_episode.requeue:1').closest('button');
    await waitFor(() => expect(button?.disabled).toBe(false));
  });
});
