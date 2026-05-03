/**
 * Tests for `applyCueText` — inline cue-text edit write-back.
 *
 * Covers SRT and ASS happy paths, line-ending preservation, ASS-styling
 * refusal, out-of-range indices, and unsupported formats.
 */

import { describe, expect, it } from 'vitest'
import {
  applyCueText,
  CueTextHasStylingError,
} from '../applyCueText'
import { CueIndexOutOfRangeError, UnsupportedFormatError } from '../applyCueTiming'

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
  '\n' +
  '[Events]\n' +
  'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' +
  'Dialogue: 0,0:00:01.50,0:00:03.20,Default,,0,0,0,,Hello there.\n' +
  'Dialogue: 0,0:00:05.00,0:00:07.50,Default,,0,0,0,,Hi, how are you?\n' +
  'Dialogue: 0,0:00:09.00,0:00:10.00,Default,,0,0,0,,Last cue.\n'

describe('applyCueText (SRT)', () => {
  it('rewrites the second cue\'s text and preserves the timing line', () => {
    const out = applyCueText({
      content: SRT_FIXTURE,
      format: 'srt',
      cueIndex: 1,
      text: 'Updated dialogue.',
    })
    expect(out).toContain('00:00:05,000 --> 00:00:07,500\nUpdated dialogue.')
    expect(out).not.toContain('General Kenobi.')
    expect(out).toContain('Hello there.') // first cue untouched
    expect(out).toContain('Last cue.') // third cue untouched
  })

  it('writes multi-line text back as separate lines', () => {
    const out = applyCueText({
      content: SRT_FIXTURE,
      format: 'srt',
      cueIndex: 0,
      text: 'Line one\nLine two',
    })
    expect(out).toContain('00:00:01,500 --> 00:00:03,200\nLine one\nLine two\n')
  })

  it('preserves CRLF line endings on the way out', () => {
    const crlf = SRT_FIXTURE.replace(/\n/g, '\r\n')
    const out = applyCueText({
      content: crlf,
      format: 'srt',
      cueIndex: 0,
      text: 'New\nText',
    })
    expect(out.includes('\r\n')).toBe(true)
    expect(out).toContain('New\r\nText')
  })

  it('throws CueIndexOutOfRangeError for too-large index', () => {
    expect(() =>
      applyCueText({ content: SRT_FIXTURE, format: 'srt', cueIndex: 99, text: 'x' }),
    ).toThrow(CueIndexOutOfRangeError)
  })
})

describe('applyCueText (ASS)', () => {
  it('rewrites the second cue\'s text without disturbing other fields', () => {
    const out = applyCueText({
      content: ASS_FIXTURE,
      format: 'ass',
      cueIndex: 1,
      text: 'Updated text',
    })
    expect(out).toContain('Dialogue: 0,0:00:05.00,0:00:07.50,Default,,0,0,0,,Updated text')
    expect(out).not.toContain('Hi, how are you?')
    expect(out).toContain('Hello there.') // cue 0 untouched
    expect(out).toContain('Last cue.') // cue 2 untouched
  })

  it('converts real newlines to \\N for ASS hard-breaks', () => {
    const out = applyCueText({
      content: ASS_FIXTURE,
      format: 'ass',
      cueIndex: 0,
      text: 'first\nsecond',
    })
    expect(out).toContain(',first\\Nsecond')
  })

  it('refuses to overwrite a cue containing override tags', () => {
    const styled =
      '[Events]\n' +
      'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n' +
      'Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\b1}Bold text{\\b0}\n'
    expect(() =>
      applyCueText({ content: styled, format: 'ass', cueIndex: 0, text: 'plain' }),
    ).toThrow(CueTextHasStylingError)
  })

  it('handles ssa as alias of ass', () => {
    const out = applyCueText({
      content: ASS_FIXTURE,
      format: 'ssa',
      cueIndex: 0,
      text: 'hi',
    })
    expect(out).toContain(',hi')
  })

  it('throws CueIndexOutOfRangeError for too-large index', () => {
    expect(() =>
      applyCueText({ content: ASS_FIXTURE, format: 'ass', cueIndex: 99, text: 'x' }),
    ).toThrow(CueIndexOutOfRangeError)
  })
})

describe('applyCueText (errors)', () => {
  it('throws UnsupportedFormatError for vtt', () => {
    expect(() =>
      applyCueText({ content: '', format: 'vtt', cueIndex: 0, text: 'x' }),
    ).toThrow(UnsupportedFormatError)
  })
})
