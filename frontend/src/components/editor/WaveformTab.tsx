/**
 * WaveformTab — backwards-compatibility re-export.
 *
 * Plan B8 Task 3 promoted this from a read-only viewer to an editing
 * surface; the implementation now lives in
 * `components/editor/waveform/WaveformEditor.tsx`. This file is kept
 * for one release as a thin wrapper so any external imports of
 * `WaveformTab` keep working during the migration window.
 *
 * To enable drag-edit, callers should migrate to `WaveformEditor` and
 * pass an `onCueChange` callback. Without one, the wrapper renders in
 * the same read-only mode as the legacy WaveformTab.
 */

import { WaveformEditor } from './waveform/WaveformEditor'

interface WaveformTabProps {
  subtitlePath: string
  videoPath: string
}

export function WaveformTab({ subtitlePath, videoPath }: WaveformTabProps) {
  return <WaveformEditor subtitlePath={subtitlePath} videoPath={videoPath} />
}
