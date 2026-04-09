/**
 * SubtitlesSettings — routing redirect.
 *
 * /settings/subtitles now redirects to /settings/subtitles/languages.
 * Content tests live in SubtitlesLanguagesPage, SubtitlesScoringPage,
 * and SubtitlesFormatPage test files.
 */
import { describe, it } from 'vitest'

describe('SubtitlesSettings redirect', () => {
  it('is a placeholder — redirect behaviour is covered by router integration tests', () => {
    // intentionally empty
  })
})
