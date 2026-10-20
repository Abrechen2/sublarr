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

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <WrongEpisodePanel language="de" />
    </QueryClientProvider>
  );
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
});
