import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SubtitlesFormatPage } from '../SubtitlesFormatPage';

const mockSaveConfig = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock('@/hooks/useApi', () => ({
  useConfig: () => ({ data: { max_ass_subtitle_size_mb: 20 }, isLoading: false }),
  useUpdateConfig: () => ({ mutate: mockSaveConfig, isPending: false }),
  useSubtitleTool: () => ({ mutate: vi.fn(), isPending: false }),
  usePreviewSubtitle: () => ({ mutate: vi.fn(), isPending: false }),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <SubtitlesFormatPage />
    </MemoryRouter>
  );
}

describe('SubtitlesFormatPage ASS size setting', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the default and saves a valid configured ASS/SSA limit', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'));

    const input = screen.getByTestId('input-max-ass-subtitle-size-mb') as HTMLInputElement;
    expect(input.value).toBe('20');
    fireEvent.change(input, { target: { value: '32' } });
    fireEvent.blur(input);

    expect(mockSaveConfig).toHaveBeenCalledWith(
      { max_ass_subtitle_size_mb: 32 },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    );
  });

  it('does not save a value outside the supported range', () => {
    renderPage();
    fireEvent.click(screen.getByTestId('settings-section-advanced-toggle'));
    const input = screen.getByTestId('input-max-ass-subtitle-size-mb');
    fireEvent.change(input, { target: { value: '51' } });
    fireEvent.blur(input);

    expect(mockSaveConfig).not.toHaveBeenCalled();
  });
});
