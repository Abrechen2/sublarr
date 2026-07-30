/**
 * Contracts for the crash-safe editor draft layer.
 *
 * The core safety property: a draft is only ever offered while the on-disk
 * mtime still matches what the draft was based on — a stale draft must never
 * be restored over a file that changed since.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  clearDraft,
  draftKey,
  loadDraft,
  MAX_DRAFT_CHARS,
  pruneStaleDrafts,
  saveDraft,
  shouldOfferDraft,
  type EditorDraft,
} from '../editorDraft';

const FILE = '/media/anime/show/ep01.de.ass';

function makeDraft(overrides: Partial<EditorDraft> = {}): EditorDraft {
  return { content: 'Dialogue: edited', mtime: 1000.5, savedAt: Date.now(), ...overrides };
}

beforeEach(() => {
  localStorage.clear();
});

describe('saveDraft / loadDraft / clearDraft', () => {
  it('round-trips a draft', () => {
    const draft = makeDraft();
    expect(saveDraft(FILE, draft)).toBe(true);
    expect(loadDraft(FILE)).toEqual(draft);
  });

  it('returns null when no draft exists', () => {
    expect(loadDraft(FILE)).toBeNull();
  });

  it('clearDraft removes the draft', () => {
    saveDraft(FILE, makeDraft());
    clearDraft(FILE);
    expect(loadDraft(FILE)).toBeNull();
  });

  it('refuses drafts above the size cap', () => {
    const huge = makeDraft({ content: 'x'.repeat(MAX_DRAFT_CHARS + 1) });
    expect(saveDraft(FILE, huge)).toBe(false);
    expect(loadDraft(FILE)).toBeNull();
  });

  it('deletes and nulls a malformed stored draft', () => {
    localStorage.setItem(draftKey(FILE), 'not json{');
    expect(loadDraft(FILE)).toBeNull();
    expect(localStorage.getItem(draftKey(FILE))).toBeNull();
  });

  it('deletes and nulls a draft with missing fields', () => {
    localStorage.setItem(draftKey(FILE), JSON.stringify({ content: 'x' }));
    expect(loadDraft(FILE)).toBeNull();
    expect(localStorage.getItem(draftKey(FILE))).toBeNull();
  });

  it('keys drafts per file path', () => {
    saveDraft(FILE, makeDraft({ content: 'A' }));
    saveDraft('/media/other.srt', makeDraft({ content: 'B' }));
    expect(loadDraft(FILE)?.content).toBe('A');
    expect(loadDraft('/media/other.srt')?.content).toBe('B');
  });
});

describe('shouldOfferDraft — the mtime safety gate', () => {
  it('offers a draft whose mtime matches and whose content differs', () => {
    const draft = makeDraft({ mtime: 1000.5, content: 'edited' });
    expect(shouldOfferDraft(draft, 1000.5, 'on-disk')).toBe(true);
  });

  it('tolerates sub-10ms mtime jitter (backend epsilon)', () => {
    const draft = makeDraft({ mtime: 1000.5, content: 'edited' });
    expect(shouldOfferDraft(draft, 1000.505, 'on-disk')).toBe(true);
  });

  it('NEVER offers a draft when the file changed on disk since', () => {
    const draft = makeDraft({ mtime: 1000.5, content: 'edited' });
    expect(shouldOfferDraft(draft, 1234.0, 'on-disk')).toBe(false);
  });

  it('does not offer a draft identical to the loaded content', () => {
    const draft = makeDraft({ mtime: 1000.5, content: 'same' });
    expect(shouldOfferDraft(draft, 1000.5, 'same')).toBe(false);
  });

  it('handles null drafts', () => {
    expect(shouldOfferDraft(null, 1000.5, 'x')).toBe(false);
  });
});

describe('pruneStaleDrafts', () => {
  it('removes drafts older than the cutoff and keeps fresh ones', () => {
    saveDraft(FILE, makeDraft({ savedAt: Date.now() - 15 * 24 * 3600 * 1000 }));
    saveDraft('/media/fresh.srt', makeDraft({ savedAt: Date.now() }));
    pruneStaleDrafts();
    expect(loadDraft(FILE)).toBeNull();
    expect(loadDraft('/media/fresh.srt')).not.toBeNull();
  });

  it('removes malformed entries', () => {
    localStorage.setItem(draftKey(FILE), '{broken');
    pruneStaleDrafts();
    expect(localStorage.getItem(draftKey(FILE))).toBeNull();
  });

  it('leaves unrelated localStorage keys alone', () => {
    localStorage.setItem('sublarr:some-pref', 'keep-me');
    pruneStaleDrafts(0);
    expect(localStorage.getItem('sublarr:some-pref')).toBe('keep-me');
  });
});
