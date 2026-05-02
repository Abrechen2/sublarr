/**
 * Tests for `applyCueTiming` (Plan B8 Task 11).
 *
 * Covers SRT and ASS write-back, edge cases (LF vs CRLF line endings,
 * commas inside ASS dialog text, malformed input), and the error
 * surface (out-of-range index, unsupported format).
 */

import { describe, expect, it } from 'vitest'
import {
  applyCueTiming,
  CueIndexOutOfRangeError,
  UnsupportedFormatError,
} from '../applyCueTiming'

const SRT_FIXTURE =
  '1\n' +
  '00:00:01,500 --> 00:00:03,200\n' +
  'Hello there.\n' +
  '\n' +
  '2\n' +
  '00:00:05,000 --> 00:00:07,500\n' +
  'General Kenobi.\n' +
  'Multi-line works.\n' +
  '\n' +
  '3\n' +
  '00:00:09,000 --> 00:00:10,000\n' +
  'Last cue.\n'

const ASS_FIXTURE =
  '[Script Info]\n' +
  'Title: Sample\n' +
  '\n' +
  '[V4+ Styles]\n' +
  'Format: Name, Fontname\n' +
  'Style: Default,Arial\n' +
  '\n' +
  '[Events]\n' +
  'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' +
  'Dialogue: 0,0:00:01.50,0:00:03.20,Default,,0,0,0,,Hello there.\n' +
  'Dialogue: 0,0:00:05.00,0:00:07.50,Default,,0,0,0,,Hi, how are you?\n' +
  'Dialogue: 0,0:00:09.00,0:00:10.00,Default,,0,0,0,,Last cue.\n'

describe('applyCueTiming (SRT)', () => {
  it('rewrites the second cue\'s timing without touching others', () => {
    const out = applyCueTiming({
      content: SRT_FIXTURE,
      format: 'srt',
      cueIndex: 1,
      start: 5.123,
      end: 7.999,
    })

    // Cue 2 timing replaced
    expect(out).toContain('00:00:05,123 --> 00:00:07,999')
    // Cue 1 unchanged
    expect(out).toContain('00:00:01,500 --> 00:00:03,200')
    // Cue 3 unchanged
    expect(out).toContain('00:00:09,000 --> 00:00:10,000')
    // Text body preserved (multi-line)
    expect(out).toContain('General Kenobi.\nMulti-line works.')
  })

  it('preserves CRLF line endings when input has them', () => {
    const crlf = SRT_FIXTURE.replace(/\n/g, '\r\n')
    const out = applyCueTiming({
      content: crlf,
      format: 'srt',
      cueIndex: 0,
      start: 1.0,
      end: 2.0,
    })

    expect(out).toContain('\r\n')
    expect(out).not.toMatch(/(?<!\r)\n/) // no LF without CR
    expect(out).toContain('00:00:01,000 --> 00:00:02,000')
  })

  it('formats sub-second values with 3-digit ms padding', () => {
    const out = applyCueTiming({
      content: SRT_FIXTURE,
      format: 'srt',
      cueIndex: 0,
      start: 0.005,
      end: 0.05,
    })
    expect(out).toContain('00:00:00,005 --> 00:00:00,050')
  })

  it('clamps negative seconds to zero (defensive)', () => {
    const out = applyCueTiming({
      content: SRT_FIXTURE,
      format: 'srt',
      cueIndex: 0,
      start: -1,
      end: 1,
    })
    expect(out).toContain('00:00:00,000 --> 00:00:01,000')
  })

  it('throws CueIndexOutOfRangeError for an index past the cue count', () => {
    expect(() =>
      applyCueTiming({
        content: SRT_FIXTURE,
        format: 'srt',
        cueIndex: 99,
        start: 0,
        end: 1,
      }),
    ).toThrow(CueIndexOutOfRangeError)
  })
})

describe('applyCueTiming (ASS)', () => {
  it('rewrites the second Dialogue line\'s timing only', () => {
    const out = applyCueTiming({
      content: ASS_FIXTURE,
      format: 'ass',
      cueIndex: 1,
      start: 5.5,
      end: 7.6,
    })

    expect(out).toContain('Dialogue: 0,0:00:05.50,0:00:07.60,Default,,0,0,0,,Hi, how are you?')
    // Other Dialogue lines untouched
    expect(out).toContain('Dialogue: 0,0:00:01.50,0:00:03.20,Default,,0,0,0,,Hello there.')
    expect(out).toContain('Dialogue: 0,0:00:09.00,0:00:10.00,Default,,0,0,0,,Last cue.')
    // Header preserved
    expect(out).toContain('[Script Info]')
    expect(out).toContain('Style: Default,Arial')
  })

  it('preserves commas inside the Text field', () => {
    const out = applyCueTiming({
      content: ASS_FIXTURE,
      format: 'ass',
      cueIndex: 1, // "Hi, how are you?" — 2 commas in text
      start: 0,
      end: 1,
    })
    expect(out).toContain('Hi, how are you?')
  })

  it('treats SSA the same as ASS', () => {
    const out = applyCueTiming({
      content: ASS_FIXTURE,
      format: 'ssa',
      cueIndex: 0,
      start: 1,
      end: 2,
    })
    expect(out).toContain('Dialogue: 0,0:00:01.00,0:00:02.00,Default,')
  })

  it('throws CueIndexOutOfRangeError when no Dialogue at that index', () => {
    expect(() =>
      applyCueTiming({
        content: ASS_FIXTURE,
        format: 'ass',
        cueIndex: 99,
        start: 0,
        end: 1,
      }),
    ).toThrow(CueIndexOutOfRangeError)
  })
})

describe('applyCueTiming (errors)', () => {
  it('throws UnsupportedFormatError for VTT (not yet supported)', () => {
    expect(() =>
      applyCueTiming({
        content: 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi.\n',
        format: 'vtt',
        cueIndex: 0,
        start: 0,
        end: 1,
      }),
    ).toThrow(UnsupportedFormatError)
  })
})
