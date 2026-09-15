# 1.14.2-rc.2 review — 2026-09-15

Base: `4ee741d7` (`master`, matching GitHub at the start of review).

## Changes

- **GH #210:** AnimeTosho checks series identity, sequel suffixes, season/episode
  numbering, and individual files in batches before creating subtitle results.
  A matching feed AniDB id cannot override a contradictory release name.
  The feed's `eid` parameter now uses `anidb_episode_id`, never `absolute_episode`.
- **GH #207:** SubSource uses the documented API v1 search/list/download flow and
  a required API key in Settings > Providers. The key is encrypted at rest,
  masked in config responses and takes effect without restarting. HTTP/schema
  errors propagate; ZIP packs select the requested episode.
- **Cleanup diagnostics:** skipped sweeps log whether `foreign_track_sweep_enabled`
  is false or no enabled `foreign_tracks` rule exists. No cleanup is enabled by
  the upgrade. `cleanup_foreign_tracks_default` is a different setting.
- `1.14.2` changelog, README and DE/EN What's New content cover the changes.
- Docker packaging excludes local `venv`/`.venv` directories. The development
  environment contained 22,819 files (0.38 GiB); it must not enter a Linux image.

## Corrections to the supplied devlog

TVSubtitles and Subf2m were already repaired by `e043842a` and shipped in 1.14.1.
GH #207 remains open for SubSource. The maintainer's 2026-09-14 issue comment
documents that distinction. Their existing endpoint regression tests still pass.

Four 0 ms sweeps do not establish that media cleanup is broken: the scheduled
entry point has its own disabled-by-default switch and needs an enabled rule.
The current production values of those two gates were not read in this review.

## Live checks

- AnimeTosho `Bleach 21` returned 27 feed entries. Several TYBW releases carried
  the original show's AniDB id (`2369`); metadata-only filtering is insufficient.
- With the fix, Bleach S02E01 / absolute 21 returns no candidates from that feed.
  The remaining original-series batch entries provided no usable subtitles.
- Positive control: **Frieren: Beyond Journey's End S01E01** returned five
  candidates. Downloading `687355:3586174` returned 1,590,207 bytes with valid ASS
  `[Script Info]` and `[Events]` sections.
- SubSource's contract was read from its official API documentation, including
  its public response examples. Successful keyed search and download are still
  **pending live verification**; no real SubSource key was available.

## Scope and limits

No database migration is introduced. AnimeTosho rejects unverified aliases and
ambiguous files; operators should use the full series title. Historical
non-numeric SubSource ids need a new search. Multiple indistinguishable subtitles
in a SubSource archive are rejected rather than selecting an arbitrary file.

The original GitNexus database failed to refresh because of a lock/WAL error.
A fresh isolated worktree of these changes was indexed successfully. Its change
analysis found only the intended provider/config/sweep/release-note changes,
with overall medium risk and four affected config-update execution flows.
The config endpoint integration test covers the new field's write/reload path.

## Sources

- [AnimeTosho issue #210](https://github.com/Abrechen2/sublarr/issues/210)
- [Provider issue #207 and maintainer update](https://github.com/Abrechen2/sublarr/issues/207#issuecomment-5668575695)
- [SubSource API documentation](https://subsource.net/api-docs)
- [AnimeTosho live feed](https://feed.animetosho.xyz/json)

## Release gate

RC target: `1.14.2-rc.2`, staging port `5766`. Stable promotion remains a separate
step after RC acceptance. Validation results are recorded below before commit.

## Validation results

- Backend full run: **7,080 passed, 20 skipped, 30 failed, one collection error**.
  All failures came from missing declared dependencies in the local virtualenv
  (`dogpile.cache` and `lingua`, with dependent adapter imports also affected).
  The same seven test files on clean `4ee741d7` reproduced **exactly 30 failures
  and one collection error**. After installing the already-declared missing
  packages, **all 53 tests in those seven files passed**. No production code or
  dependency manifest change was needed to resolve them.
- Final targeted regressions: **48 passed** (AnimeTosho, SubSource, sweep gates).
  Config masking/valid keys and existing scraper tests: **67 passed**.
- Frontend: **1,313 tests passed in 142 files**; ESLint and TypeScript passed.
- Backend Ruff lint and formatting passed for the full backend (1,254 files).
- Production frontend dependency license check passed.
- Local `linux/amd64` Docker image built. Health returned HTTP 200,
  `status=healthy`, `version=1.14.2-rc.2`. The image has neither `/app/venv` nor
  `/app/.venv`. Its gunicorn arguments match the Dockerfile command.
- No SubSource keyed live test, ARM64 build, registry publication or RC-server
  deployment has been performed as part of this preparation.
