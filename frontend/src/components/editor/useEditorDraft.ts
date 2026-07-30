/**
 * useEditorDraft — debounced crash-safe draft mirroring.
 *
 * While the editor is dirty, the current content is persisted to
 * localStorage (debounced) so a browser crash or killed tab loses at most
 * ~1 s of work. On the dirty→clean transition (save succeeded, or the user
 * undid back to the on-disk baseline) the draft is deleted — but an editor
 * that OPENS clean never touches an existing draft, so the restore offer in
 * SubtitleEditorModal can still read it.
 */

import { useEffect, useRef } from 'react';
import { clearDraft, saveDraft } from './editorDraft';

const DRAFT_DEBOUNCE_MS = 1000;

export function useEditorDraft(
  filePath: string | null,
  content: string | null,
  mtime: number | null,
  dirty: boolean
): void {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasDirty = useRef(false);
  const prevFilePath = useRef(filePath);

  useEffect(() => {
    if (filePath !== prevFilePath.current) {
      prevFilePath.current = filePath;
      wasDirty.current = false;
    }
    if (!filePath) return;

    if (timer.current) clearTimeout(timer.current);

    if (!dirty || content === null || mtime === null) {
      // Only clear on a dirty→clean transition. An editor that opens clean
      // must not delete a draft another (crashed) session left behind.
      if (wasDirty.current) {
        clearDraft(filePath);
        wasDirty.current = false;
      }
      return;
    }

    wasDirty.current = true;
    const snapshot = { content, mtime, savedAt: Date.now() };
    timer.current = setTimeout(() => {
      saveDraft(filePath, snapshot);
    }, DRAFT_DEBOUNCE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [filePath, content, mtime, dirty]);
}
