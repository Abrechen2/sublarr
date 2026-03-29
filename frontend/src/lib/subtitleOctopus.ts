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
// Vite wraps CJS modules as { default: ctor } — we extract the actual constructor.
import * as _LibassWasm from 'libass-wasm'
const _ctor = (_LibassWasm as any).default ?? _LibassWasm
export const SubtitleOctopus = _ctor as unknown as SubtitleOctopusConstructor
