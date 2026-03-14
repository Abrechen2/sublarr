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
export interface ISubtitleOctopus {
  setTrackByUrl(url: string): void
  setTrack(content: string): void
  freeTrack(): void
  dispose(): void
}

export interface SubtitleOctopusConstructor {
  new (options: SubtitleOctopusOptions): ISubtitleOctopus
}

// libass-wasm is a CJS module with no TypeScript declarations.
// We import it as a namespace (no esModuleInterop needed) and cast to our typed interface.
import * as _LibassWasm from 'libass-wasm'
export const SubtitleOctopus = _LibassWasm as unknown as SubtitleOctopusConstructor
