/**
 * Typed wrapper for libass-wasm (JavascriptSubtitlesOctopus).
 * Renders ASS/SRT subtitles natively in the browser via libass compiled to WASM.
 *
 * The npm package `libass-wasm` ships no TypeScript declarations, so we declare
 * the minimal interface we need here.
 */

export interface SubtitleOctopusOptions {
  video: HTMLVideoElement
  subUrl?: string
  subContent?: string
  workerUrl: string
  legacyWorkerUrl?: string
  fonts?: string[]
  availableFonts?: Record<string, string>
  onReady?: () => void
  onError?: (err: unknown) => void
}

// libass-wasm has no @types — declare minimal interface
declare class SubtitlesOctopusClass {
  constructor(options: SubtitleOctopusOptions)
  setTrackByUrl(url: string): void
  setTrack(content: string): void
  freeTrack(): void
  dispose(): void
}

// eslint-disable-next-line @typescript-eslint/no-require-imports
const SubtitleOctopus: typeof SubtitlesOctopusClass = require('libass-wasm')

export { SubtitleOctopus }
