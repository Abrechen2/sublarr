The JSON references come from an independent ffmpeg 7.1.5 / libass 0.17.3
rendering experiment on 2026-09-20. Each synthetic event containing HELLO was
rendered and compared with a visible text control using the same overrides
followed by an explicit drawing reset. No Sublarr helper supplied expectations.

288 deliberate cases and 512 subsequent seeded combinations (seed 20260920)
were rendered. Seventeen masked/clipped controls were inconclusive and omitted.
Of the remaining 783 cases, one contains a physical carriage return and must
require review instead of being classified as a safe subtitle event.

The parser reference is libass/ass_parse.c at tag 0.17.3:
https://github.com/libass/libass/blob/0.17.3/libass/ass_parse.c

These are drawing-state references, not a general ASS conformance corpus.
