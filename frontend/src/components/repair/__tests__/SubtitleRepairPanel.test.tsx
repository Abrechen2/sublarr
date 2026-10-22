import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SubtitleRepairPanel } from '../SubtitleRepairPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const mockStart = vi.fn();
const mockScan = vi.fn();
vi.mock('@/api/system/repair', () => ({
  scanDamaged: (language?: string) => mockScan(language),
  startRepair: (opts: unknown) => mockStart(opts),
  getRepairStatus: () =>
    Promise.resolve({ running: false, done: 0, total: 0, deferred: 0, local_only: false }),
  scanWrongEpisodes: vi.fn(),
  requeueWrongEpisodes: vi.fn(),
}));

const scan = {
  damaged: 7306,
  recoverable_from_backup: 3401,
  needs_download: 3905,
  needs_download_by_provider: { opensubtitles: 3836 },
  untouched: 0,
  missing_from_disk: 0,
  unresolvable: 0,
  quarantined: 0,
  already_repaired: 0,
  partially_repaired: 0,
  partially_repaired_files: [],
};

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SubtitleRepairPanel />
    </QueryClientProvider>,
  );
}

describe('SubtitleRepairPanel', () => {
  beforeEach(() => {
    mockStart.mockReset().mockResolvedValue(undefined);
    mockScan.mockReset().mockResolvedValue(scan);
  });

  it('restores from backups only without touching a provider', async () => {
    renderPanel();
    fireEvent.click(screen.getByText('repair.scan'));
    await waitFor(() => expect(screen.getByText('repair.start_local').closest('button')).toBeEnabled());

    fireEvent.click(screen.getByText('repair.start_local'));

    await waitFor(() =>
      expect(mockStart).toHaveBeenCalledWith({ language: 'de', dry_run: false, local_only: true }),
    );
  });

  it('runs the dry run without a limit, since it downloads nothing', async () => {
    renderPanel();
    fireEvent.click(screen.getByText('repair.scan'));
    await waitFor(() => expect(screen.getByText('repair.dry_run').closest('button')).toBeEnabled());

    fireEvent.click(screen.getByText('repair.dry_run'));

    await waitFor(() =>
      expect(mockStart).toHaveBeenCalledWith({ language: 'de', dry_run: true, local_only: false }),
    );
  });
});
