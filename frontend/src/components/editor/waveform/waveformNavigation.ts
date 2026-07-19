/**
 * Marker-jump navigation for the waveform editor.
 *
 * Turns the passive marker overlays (keyframes, scene cuts) and the detected
 * timing defects (gaps / overlaps) into navigable anchors: from the current
 * playhead, jump to the nearest marker in a direction. Pure so the "which
 * marker is next" logic is unit-testable without wavesurfer.
 */

/**
 * Return the nearest marker strictly after (`next`) or before (`prev`)
 * `currentSec`, or `null` when there is none in that direction. Input need not
 * be sorted; non-finite entries are ignored. Strict inequality means a marker
 * exactly at the playhead is skipped, so repeated presses always advance.
 */
export function findAdjacentMarker(
  markersSec: readonly number[],
  currentSec: number,
  direction: 'next' | 'prev',
): number | null {
  let best: number | null = null
  for (const m of markersSec) {
    if (!Number.isFinite(m)) continue
    if (direction === 'next') {
      if (m > currentSec && (best === null || m < best)) best = m
    } else if (m < currentSec && (best === null || m > best)) {
      best = m
    }
  }
  return best
}
