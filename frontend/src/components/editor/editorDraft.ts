/**
 * Crash-safe draft persistence for the subtitle editor.
 *
 * The modal's `beforeunload` guard only covers deliberate closes — a browser
 * crash or killed tab discards unsaved work. Every dirty edit is therefore
 * mirrored (debounced) into localStorage, keyed by file path, together with
 * the on-disk mtime it was based on. On the next open the draft is offered
 * for restore — but ONLY while the file's mtime still matches: if the file
 * changed on disk in the meantime, silently restoring the draft would let a
 * later save clobber the newer file, so a stale draft is dropped instead
 * (same philosophy as the backend's optimistic-concurrency check).
 */

export interface EditorDraft {
  content: string;
  /** On-disk mtime (seconds, from GET /tools/content) the draft was based on. */
  mtime: number;
  /** Wall-clock ms when the draft was persisted (for display + pruning). */
  savedAt: number;
}

const KEY_PREFIX = 'sublarr:editor-draft:';

/** Drafts larger than this are not persisted (localStorage quota safety). */
export const MAX_DRAFT_CHARS = 2_000_000;

/** Drafts older than this are pruned on editor open. */
const MAX_DRAFT_AGE_MS = 14 * 24 * 60 * 60 * 1000;

/** Tolerance when comparing mtimes — mirrors the backend's 0.01 s check. */
const MTIME_EPSILON = 0.01;

export function draftKey(filePath: string): string {
  return `${KEY_PREFIX}${filePath}`;
}

/**
 * Persist a draft. Returns false when the draft was not stored (too large,
 * storage unavailable, or quota exhausted even after pruning).
 */
export function saveDraft(filePath: string, draft: EditorDraft): boolean {
  if (draft.content.length > MAX_DRAFT_CHARS) return false;
  const payload = JSON.stringify(draft);
  try {
    localStorage.setItem(draftKey(filePath), payload);
    return true;
  } catch {
    // Quota exhausted — drop the oldest drafts and retry once.
    pruneStaleDrafts(0);
    try {
      localStorage.setItem(draftKey(filePath), payload);
      return true;
    } catch {
      return false;
    }
  }
}

export function loadDraft(filePath: string): EditorDraft | null {
  let raw: string | null;
  try {
    raw = localStorage.getItem(draftKey(filePath));
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      typeof (parsed as EditorDraft).content === 'string' &&
      typeof (parsed as EditorDraft).mtime === 'number' &&
      typeof (parsed as EditorDraft).savedAt === 'number'
    ) {
      return parsed as EditorDraft;
    }
  } catch {
    // fall through — malformed drafts are deleted below
  }
  clearDraft(filePath);
  return null;
}

export function clearDraft(filePath: string): void {
  try {
    localStorage.removeItem(draftKey(filePath));
  } catch {
    // storage unavailable — nothing to clear
  }
}

/**
 * Whether a loaded draft should be offered for restore: the on-disk mtime
 * must still match what the draft was based on, and the draft must actually
 * differ from the loaded content.
 */
export function shouldOfferDraft(
  draft: EditorDraft | null,
  currentMtime: number,
  currentContent: string
): draft is EditorDraft {
  if (!draft) return false;
  if (Math.abs(draft.mtime - currentMtime) > MTIME_EPSILON) return false;
  return draft.content !== currentContent;
}

/**
 * Delete drafts older than `maxAgeMs` (default 14 days). Called on editor
 * open so abandoned drafts don't accumulate toward the storage quota.
 */
export function pruneStaleDrafts(maxAgeMs: number = MAX_DRAFT_AGE_MS): void {
  let keys: string[];
  try {
    keys = Object.keys(localStorage).filter(k => k.startsWith(KEY_PREFIX));
  } catch {
    return;
  }
  const now = Date.now();
  for (const key of keys) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      const parsed: unknown = JSON.parse(raw);
      const savedAt =
        typeof parsed === 'object' && parsed !== null ? (parsed as EditorDraft).savedAt : undefined;
      if (typeof savedAt !== 'number' || now - savedAt >= maxAgeMs) {
        localStorage.removeItem(key);
      }
    } catch {
      try {
        localStorage.removeItem(key);
      } catch {
        // storage unavailable — give up on this key
      }
    }
  }
}
