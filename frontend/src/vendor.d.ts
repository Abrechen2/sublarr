/**
 * Minimal TypeScript declarations for third-party packages without official @types.
 */

declare module 'plyr' {
  export interface PlyrOptions {
    controls?: string[]
    keyboard?: { focused?: boolean; global?: boolean }
    tooltips?: { controls?: boolean; seek?: boolean }
    captions?: { active?: boolean }
    fullscreen?: { enabled?: boolean; fallback?: boolean }
    speed?: { selected?: number; options?: number[] }
    clickToPlay?: boolean
    disableContextMenu?: boolean
    ratio?: string
  }

  class Plyr {
    constructor(target: HTMLElement | string, options?: PlyrOptions)
    currentTime: number
    readonly media: HTMLMediaElement
    destroy(callback?: () => void): void
    on(event: string, callback: (event: Event) => void): void
  }

  export default Plyr
}
