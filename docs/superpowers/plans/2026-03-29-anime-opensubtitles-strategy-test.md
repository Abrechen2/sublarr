# Anime OpenSubtitles Strategy Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python test harness outside Sublarr that empirically evaluates every plausible OpenSubtitles search strategy for anime episode-numbering mismatches, and produces a ranked recommendation report.

**Architecture:** A self-contained script directory (`D:/Sublarr_Projekt/anime_subtitle_test/`) with no dependency on Sublarr code. Calls the OpenSubtitles REST API directly via `requests`. Iterates over a matrix of (strategy × test-case) pairs, collects result counts and quality signals, and saves a JSON report + console summary.

**Tech Stack:** Python 3.12, `requests`, `tabulate` (for console table), stdlib only beyond that.

---

## Background: The Problem

OpenSubtitles indexes many anime as a **single season with absolute episode numbers** (e.g. "S01E27"), while Sonarr/TVDB splits them into multiple seasons (e.g. "S02E15"). When Sublarr searches with `season=2, episode=15` it gets 0 results. A fix was merged that retries with `season=1, episode=<absolute>` — but we don't yet know which of all possible strategies is truly best across the full landscape of anime.

This test harness answers that empirically.

---

## Test Cases

Five series (four with known mismatches + one control):

| ID | Series | Sonarr S/E | IMDB ID | Absolute Ep | Ep Title | Notes |
|----|--------|-----------|---------|-------------|----------|-------|
| TC1 | 86 EIGHTY-SIX | S02E15 | tt14950550 | 23 | Welcome Back | Known 0-result case in Sublarr |
| TC2 | Attack on Titan | S04E29 | tt2560140 | 87 | Retrospective | Final season multi-cour split |
| TC3 | Demon Slayer | S03E11 | tt9335498 | 44 | No Matter How Many Lives | Swordsmith Village arc |
| TC4 | Vinland Saga | S02E24 | tt8009460 | 48 | End of the Prologue | S2 rarely on OpenSubtitles |
| TC5 | One Piece (control) | S01E100 | tt0388629 | 100 | Vivi's Adventure | S1 only, no mismatch expected |

> **Note on episode titles:** Verify titles against your Sonarr/Plex before running — titles are used for S14 (episode_title strategy). TC1 "Welcome Back" is confirmed from a real subtitle filename.

---

## Strategies Under Test (17 total)

### Parameter-space coverage

| # | Name | imdb / parent_imdb / tmdb | season | episode | query | languages | Notes |
|---|------|--------------------------|--------|---------|-------|-----------|-------|
| S1 | `standard` | imdb | Sonarr S | Sonarr E | – | ✓ | Baseline — current Sublarr before fix |
| S2 | `abs_fallback` | imdb | 1 | absolute | – | ✓ | Current Sublarr fix |
| S3 | `abs_always` | imdb | 1 | absolute | – | ✓ | Like S2 but also applies for season=1 |
| S4 | `imdb_no_se` | imdb | – | – | – | ✓ | No S/E filter at all |
| S5 | `title_standard` | – | Sonarr S | Sonarr E | series title | ✓ | No IMDB |
| S6 | `title_abs` | – | 1 | absolute | series title | ✓ | Title + absolute |
| S7 | `title_only` | – | – | – | series title | ✓ | Title only, no numbers |
| S8 | `merged` | imdb | both | both | – | ✓ | S1 + S2 deduped — 2 API calls |
| S9 | `hash` | – | – | – | – | ✓ | moviehash — needs video file path |
| S10 | `parent_imdb_standard` | parent_imdb | Sonarr S | Sonarr E | – | ✓ | Series as parent IMDB |
| S11 | `parent_imdb_abs` | parent_imdb | 1 | absolute | – | ✓ | Parent IMDB + absolute |
| S12 | `imdb_no_lang` | imdb | Sonarr S | Sonarr E | – | – | No language filter, client-side filter |
| S13 | `abs_no_lang` | imdb | 1 | absolute | – | – | Absolute + no language filter |
| S14 | `episode_title` | – | – | – | ep title | ✓ | Episode title as query |
| S15 | `cascade` | imdb | adaptive | adaptive | adaptive | ✓ | hash → abs → standard → no_se → title_abs → title_only; stop at first hit |
| S16 | `abs_plus_one` | imdb | 1 | absolute+1 | – | ✓ | Off-by-one: abs+1 |
| S17 | `abs_minus_one` | imdb | 1 | absolute-1 | – | ✓ | Off-by-one: abs-1 |

### Why each new strategy matters

- **S9 hash**: File binary → hash lookup bypasses all numbering. Best possible result if file is accessible.
- **S10/S11 parent_imdb**: OpenSubtitles distinguishes `imdb_id` (episode's own IMDB) from `parent_imdb_id` (series IMDB). For most anime, the series IMDB is what uploaders attach to subtitles.
- **S12/S13 no_lang**: Language tags on OpenSubtitles are user-entered and sometimes wrong (e.g. "German" tagged as "en"). Without filter we get all candidates and filter client-side.
- **S14 episode_title**: Subtitle files are often named after the episode title (e.g. `86.S02E15.Welcome.Back.de.ass`). Query-searching by title finds these even when S/E is wrong.
- **S15 cascade**: What Sublarr should actually implement — minimal API calls, best result. The order matters and this test will reveal the optimal order.
- **S16/S17 off-by-one**: AniDB absolute counting diverges from TVDB by ±1 when specials/OVAs are included in one database but not the other. Common enough to warrant a test.

---

## Metrics Per (Strategy × TestCase)

| Metric | Description |
|--------|-------------|
| `result_count` | Total subtitle entries returned |
| `de_count` | Entries where `language == tc.language` |
| `top_filename` | Filename of first result |
| `correct_ep` | Bool — does top filename match expected S/E or absolute ep? |
| `correct_ep_why` | Human-readable match explanation |
| `latency_ms` | Total API call time |
| `api_calls` | Number of HTTP requests made |
| `skipped` | Bool — strategy skipped (e.g. hash with no file) |

---

## File Structure

```
D:/Sublarr_Projekt/anime_subtitle_test/
  requirements.txt    ← requests, tabulate
  config.py           ← API key + test case definitions (all 5 cases, all metadata)
  strategies.py       ← 17 strategy functions + ALL_STRATEGIES list
  metrics.py          ← extract quality signals from raw API response
  runner.py           ← matrix runner: strategies × test_cases → list[Result]
  report.py           ← console table + JSON output + ranking
  run_test.py         ← entry point with --tc / --strategy / --file-path CLI flags
  test_smoke.py       ← offline unit tests (no API key needed)
  results/            ← created at runtime; timestamped JSON files
```

---

## Task 1: Project Scaffold + Requirements

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/requirements.txt`
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/results/.gitkeep`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p D:/Sublarr_Projekt/anime_subtitle_test/results
```

- [ ] **Step 2: Write requirements.txt**

```
requests==2.31.0
tabulate==0.9.0
```

- [ ] **Step 3: Install**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
pip install -r requirements.txt
```

- [ ] **Step 4: Verify**

```bash
python -c "import requests, tabulate; print('OK')"
```

Expected: `OK`

---

## Task 2: config.py — Credentials + Test Cases

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/config.py`

- [ ] **Step 1: Write config.py**

```python
"""API credentials and test case definitions."""
import os

OS_API_KEY = os.environ.get("OS_API_KEY", "")
OS_USER_AGENT = "SublarrTest v0.1"
OS_BASE_URL = "https://api.opensubtitles.com/api/v1"


def get_api_key() -> str:
    key = OS_API_KEY.strip()
    if not key:
        raise RuntimeError(
            "No OpenSubtitles API key.\n"
            "Set: export OS_API_KEY=<your_key>\n"
            "Copy from Sublarr Settings → Providers → OpenSubtitles."
        )
    return key


# ---------------------------------------------------------------------------
# Test cases — all metadata needed by all 17 strategies
#
# Fields:
#   id             short identifier
#   series         display name
#   imdb_id        series IMDB ID without 'tt' prefix (str)
#   parent_imdb_id same as imdb_id for top-level series; episode-level if known
#   season         Sonarr/TVDB season (int)
#   episode        Sonarr/TVDB episode (int)
#   absolute       AniDB absolute episode number (int)
#   ep_title       episode title string for S14 (str)
#   title          series title for title-based searches (str)
#   language       ISO 639-1 code to filter results (str)
#   file_path      optional: absolute path to the local video file for hash (str|None)
#   note           expected challenge description
# ---------------------------------------------------------------------------
TEST_CASES = [
    {
        "id": "TC1",
        "series": "86 EIGHTY-SIX",
        "imdb_id": "14950550",
        "parent_imdb_id": "14950550",
        "season": 2,
        "episode": 15,
        "absolute": 23,
        "ep_title": "Welcome Back",
        "title": "86 EIGHTY-SIX",
        "language": "de",
        "file_path": None,          # set to actual video path to enable hash strategy
        "note": "Known 0-result with standard S/E; Crunchyroll split S2",
    },
    {
        "id": "TC2",
        "series": "Attack on Titan",
        "imdb_id": "2560140",
        "parent_imdb_id": "2560140",
        "season": 4,
        "episode": 29,
        "absolute": 87,
        "ep_title": "Retrospective",
        "title": "Attack on Titan",
        "language": "de",
        "file_path": None,
        "note": "Final season split across S4P1/S4P2/S4P3 on TVDB",
    },
    {
        "id": "TC3",
        "series": "Demon Slayer",
        "imdb_id": "9335498",
        "parent_imdb_id": "9335498",
        "season": 3,
        "episode": 11,
        "absolute": 44,
        "ep_title": "No Matter How Many Lives",
        "title": "Demon Slayer: Kimetsu no Yaiba",
        "language": "de",
        "file_path": None,
        "note": "Swordsmith Village Arc; S3 = cour 3 absolute",
    },
    {
        "id": "TC4",
        "series": "Vinland Saga",
        "imdb_id": "8009460",
        "parent_imdb_id": "8009460",
        "season": 2,
        "episode": 24,
        "absolute": 48,
        "ep_title": "End of the Prologue",
        "title": "Vinland Saga",
        "language": "de",
        "file_path": None,
        "note": "S2 — verify if OpenSubtitles uses absolute for this",
    },
    {
        "id": "TC5",
        "series": "One Piece (control)",
        "imdb_id": "388629",
        "parent_imdb_id": "388629",
        "season": 1,
        "episode": 100,
        "absolute": 100,           # S1 only → absolute == episode
        "ep_title": "Vivi's Adventure",
        "title": "One Piece",
        "language": "de",
        "file_path": None,
        "note": "Control: season=1, absolute==episode; all strategies should find results",
    },
]
```

- [ ] **Step 2: Set optional file_path for hash testing**

If you have the actual video file for TC1, edit `config.py` and set:
```python
"file_path": r"Z:\Anime\86 EIGHTY-SIX\Season 02\86 - S02E15 - Welcome Back.mkv",
```
Leave as `None` if the file is not available — the hash strategy will be skipped gracefully.

- [ ] **Step 3: Verify**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
python -c "from config import TEST_CASES; print(f'{len(TEST_CASES)} test cases loaded')"
```

Expected: `5 test cases loaded`

---

## Task 3: strategies.py — All 17 Search Strategies

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/strategies.py`

- [ ] **Step 1: Write strategies.py**

```python
"""Seventeen OpenSubtitles search strategies for anime episode-numbering mismatches."""
import hashlib
import struct
import time
from pathlib import Path

import requests

from config import OS_BASE_URL

# Sentinel returned when a strategy is intentionally skipped (e.g. hash with no file)
SKIPPED = "__SKIPPED__"


def _search(session: requests.Session, params: dict) -> tuple[list[dict], int]:
    """Call /subtitles, return (items, latency_ms). Raises on auth/rate errors."""
    t0 = time.monotonic()
    resp = session.get(f"{OS_BASE_URL}/subtitles", params=params)
    latency_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code in (401, 403):
        raise RuntimeError(f"OpenSubtitles auth error: HTTP {resp.status_code}")
    if resp.status_code == 429:
        raise RuntimeError("Rate limit hit — retry after 10s")
    if resp.status_code != 200:
        return [], latency_ms

    return resp.json().get("data", []), latency_ms


def _compute_hash(file_path: str) -> str | None:
    """Compute OpenSubtitles-style hash (first + last 64 KB XOR with file size)."""
    try:
        path = Path(file_path)
        file_size = path.stat().st_size
        if file_size < 131072:  # 128 KB minimum
            return None
        chunk = 65536
        fmt = "<q"  # signed 64-bit little-endian
        hash_value = file_size
        with open(path, "rb") as f:
            for _ in range(chunk // 8):
                buf = f.read(8)
                if len(buf) < 8:
                    break
                (val,) = struct.unpack(fmt, buf)
                hash_value = (hash_value + val) & 0xFFFFFFFFFFFFFFFF
            f.seek(-chunk, 2)
            for _ in range(chunk // 8):
                buf = f.read(8)
                if len(buf) < 8:
                    break
                (val,) = struct.unpack(fmt, buf)
                hash_value = (hash_value + val) & 0xFFFFFFFFFFFFFFFF
        return f"{hash_value:016x}"
    except Exception:
        return None


def _result(strategy: str, items: list, ms: int, calls: int, params: list) -> dict:
    return {
        "strategy": strategy,
        "items": items,
        "latency_ms": ms,
        "api_calls": calls,
        "params": params,
        "skipped": False,
    }


def _skipped(strategy: str, reason: str) -> dict:
    return {
        "strategy": strategy,
        "items": [],
        "latency_ms": 0,
        "api_calls": 0,
        "params": [],
        "skipped": True,
        "skip_reason": reason,
    }


# ---------------------------------------------------------------------------
# S1 — Standard: IMDB + Sonarr S/E + language  (baseline, Sublarr before fix)
# ---------------------------------------------------------------------------
def strategy_standard(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": tc["season"],
         "episode_number": tc["episode"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("standard", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S2 — Abs fallback: IMDB + season=1 + absolute episode  (current Sublarr fix)
# ---------------------------------------------------------------------------
def strategy_abs_fallback(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": 1,
         "episode_number": tc["absolute"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("abs_fallback", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S3 — Abs always: same as S2 but explicitly run for all test cases including S1
# ---------------------------------------------------------------------------
def strategy_abs_always(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": 1,
         "episode_number": tc["absolute"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("abs_always", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S4 — IMDB only: no season/episode filter at all
# ---------------------------------------------------------------------------
def strategy_imdb_no_se(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("imdb_no_se", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S5 — Title + standard S/E: title string, no IMDB
# ---------------------------------------------------------------------------
def strategy_title_standard(tc: dict, session: requests.Session) -> dict:
    p = {"query": tc["title"], "season_number": tc["season"],
         "episode_number": tc["episode"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("title_standard", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S6 — Title + absolute: title string + season=1 + absolute episode
# ---------------------------------------------------------------------------
def strategy_title_abs(tc: dict, session: requests.Session) -> dict:
    p = {"query": tc["title"], "season_number": 1,
         "episode_number": tc["absolute"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("title_abs", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S7 — Title only: no season, no episode, no IMDB
# ---------------------------------------------------------------------------
def strategy_title_only(tc: dict, session: requests.Session) -> dict:
    p = {"query": tc["title"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("title_only", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S8 — Merged: S1 + S2 combined, deduplicated by file_id
# ---------------------------------------------------------------------------
def strategy_merged(tc: dict, session: requests.Session) -> dict:
    r1 = strategy_standard(tc, session)
    r2 = strategy_abs_fallback(tc, session)
    seen: set = set()
    merged = []
    for item in r1["items"] + r2["items"]:
        files = item.get("attributes", {}).get("files", [])
        fid = files[0].get("file_id") if files else None
        if fid is not None and fid not in seen:
            seen.add(fid)
            merged.append(item)
    return _result("merged", merged, r1["latency_ms"] + r2["latency_ms"], 2,
                   r1["params"] + r2["params"])


# ---------------------------------------------------------------------------
# S9 — Hash: moviehash lookup — most accurate, skipped if no file_path set
# ---------------------------------------------------------------------------
def strategy_hash(tc: dict, session: requests.Session) -> dict:
    file_path = tc.get("file_path")
    if not file_path:
        return _skipped("hash", "no file_path set in test case")
    file_hash = _compute_hash(file_path)
    if not file_hash:
        return _skipped("hash", f"could not compute hash for {file_path}")
    p = {"moviehash": file_hash, "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("hash", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S10 — Parent IMDB + standard S/E
# OpenSubtitles parent_imdb_id = series-level IMDB vs episode-level imdb_id
# ---------------------------------------------------------------------------
def strategy_parent_imdb_standard(tc: dict, session: requests.Session) -> dict:
    p = {"parent_imdb_id": tc["parent_imdb_id"], "season_number": tc["season"],
         "episode_number": tc["episode"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("parent_imdb_standard", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S11 — Parent IMDB + absolute episode
# ---------------------------------------------------------------------------
def strategy_parent_imdb_abs(tc: dict, session: requests.Session) -> dict:
    p = {"parent_imdb_id": tc["parent_imdb_id"], "season_number": 1,
         "episode_number": tc["absolute"], "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("parent_imdb_abs", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S12 — IMDB + standard S/E, WITHOUT language filter → client-side filter
# Tests whether OS language tags are causing false negatives
# ---------------------------------------------------------------------------
def strategy_imdb_no_lang(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": tc["season"],
         "episode_number": tc["episode"]}
    items, ms = _search(session, p)
    # Client-side: keep all, report de_count separately in metrics
    return _result("imdb_no_lang", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S13 — IMDB + absolute, WITHOUT language filter
# ---------------------------------------------------------------------------
def strategy_abs_no_lang(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": 1,
         "episode_number": tc["absolute"]}
    items, ms = _search(session, p)
    return _result("abs_no_lang", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S14 — Episode title as query string
# Many subtitle filenames include the episode title — this finds them even
# when S/E is wrong on OpenSubtitles.
# Skipped if ep_title is empty.
# ---------------------------------------------------------------------------
def strategy_episode_title(tc: dict, session: requests.Session) -> dict:
    ep_title = tc.get("ep_title", "").strip()
    if not ep_title:
        return _skipped("episode_title", "no ep_title in test case")
    p = {"query": ep_title, "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("episode_title", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S15 — Cascade: progressive fallback, stop at first strategy that returns hits
# Order: hash → abs_fallback → standard → imdb_no_se → title_abs → title_only
# This is what Sublarr should implement — minimize calls, maximize hit rate.
# ---------------------------------------------------------------------------
def strategy_cascade(tc: dict, session: requests.Session) -> dict:
    total_ms = 0
    total_calls = 0
    all_params: list[dict] = []
    tried: list[str] = []

    steps = [
        strategy_hash,
        strategy_abs_fallback,
        strategy_standard,
        strategy_imdb_no_se,
        strategy_title_abs,
        strategy_title_only,
    ]

    for step_fn in steps:
        r = step_fn(tc, session)
        total_ms += r["latency_ms"]
        total_calls += r["api_calls"]
        all_params.extend(r["params"])
        tried.append(r["strategy"])

        if r.get("skipped"):
            continue
        if r["items"]:
            return {
                "strategy": "cascade",
                "items": r["items"],
                "latency_ms": total_ms,
                "api_calls": total_calls,
                "params": all_params,
                "skipped": False,
                "cascade_winner": r["strategy"],
                "cascade_tried": tried,
            }

    return {
        "strategy": "cascade",
        "items": [],
        "latency_ms": total_ms,
        "api_calls": total_calls,
        "params": all_params,
        "skipped": False,
        "cascade_winner": None,
        "cascade_tried": tried,
    }


# ---------------------------------------------------------------------------
# S16 — Off-by-one: absolute + 1
# AniDB/TVDB specials-counting diverges by ±1
# ---------------------------------------------------------------------------
def strategy_abs_plus_one(tc: dict, session: requests.Session) -> dict:
    p = {"imdb_id": tc["imdb_id"], "season_number": 1,
         "episode_number": tc["absolute"] + 1, "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("abs_plus_one", items, ms, 1, [p])


# ---------------------------------------------------------------------------
# S17 — Off-by-one: absolute - 1
# ---------------------------------------------------------------------------
def strategy_abs_minus_one(tc: dict, session: requests.Session) -> dict:
    abs_ep = tc["absolute"]
    if abs_ep <= 1:
        return _skipped("abs_minus_one", "absolute episode is 1, abs-1 would be 0")
    p = {"imdb_id": tc["imdb_id"], "season_number": 1,
         "episode_number": abs_ep - 1, "languages": tc["language"]}
    items, ms = _search(session, p)
    return _result("abs_minus_one", items, ms, 1, [p])


ALL_STRATEGIES = [
    strategy_standard,
    strategy_abs_fallback,
    strategy_abs_always,
    strategy_imdb_no_se,
    strategy_title_standard,
    strategy_title_abs,
    strategy_title_only,
    strategy_merged,
    strategy_hash,
    strategy_parent_imdb_standard,
    strategy_parent_imdb_abs,
    strategy_imdb_no_lang,
    strategy_abs_no_lang,
    strategy_episode_title,
    strategy_cascade,
    strategy_abs_plus_one,
    strategy_abs_minus_one,
]
```

- [ ] **Step 2: Verify**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
python -c "from strategies import ALL_STRATEGIES; print(f'{len(ALL_STRATEGIES)} strategies loaded')"
```

Expected: `17 strategies loaded`

---

## Task 4: metrics.py — Quality Signal Extraction

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/metrics.py`

- [ ] **Step 1: Write metrics.py**

```python
"""Extract quality metrics from a raw OpenSubtitles API response."""
import re


def extract_metrics(items: list[dict], tc: dict) -> dict:
    """
    Returns:
      result_count   total items in response
      de_count       items with language == tc["language"]
      top_filename   filename of first result
      correct_ep     bool: does top_filename match expected episode?
      correct_ep_why human-readable explanation
    """
    result_count = len(items)
    lang = tc["language"]
    de_count = sum(
        1 for item in items
        if item.get("attributes", {}).get("language", "") == lang
    )

    top_filename = ""
    if items:
        files = items[0].get("attributes", {}).get("files", [])
        if files:
            top_filename = files[0].get("file_name", "")

    correct_ep, correct_ep_why = _check_correct_episode(top_filename, tc)

    return {
        "result_count": result_count,
        "de_count": de_count,
        "top_filename": top_filename,
        "correct_ep": correct_ep,
        "correct_ep_why": correct_ep_why,
    }


def _check_correct_episode(filename: str, tc: dict) -> tuple[bool, str]:
    if not filename:
        return False, "no results"

    fn = filename.lower()
    s = tc["season"]
    e = tc["episode"]
    ab = tc["absolute"]

    # Standard S/E notation: S02E15
    if re.search(rf"s{s:02d}e{e:02d}", fn):
        return True, f"matched S{s:02d}E{e:02d}"

    # Absolute as S01ExX: S01E23 / S01E023
    for fmt in (rf"s01e{ab:02d}[^0-9]", rf"s01e{ab:03d}[^0-9]"):
        if re.search(fmt, fn + " "):  # pad to avoid truncation edge case
            return True, f"matched S01E{ab:02d} (absolute as S1)"

    # Bare absolute episode number surrounded by non-digits: .23. or _23_ or - 23 -
    if re.search(rf"(?<![0-9]){ab:02d}(?![0-9])", fn):
        return True, f"matched bare absolute episode {ab}"

    # Episode title substring (lower-cased)
    ep_title = tc.get("ep_title", "").lower().strip()
    if ep_title and ep_title in fn:
        return True, f"matched episode title '{tc['ep_title']}'"

    return False, f"no match for S{s:02d}E{e:02d} / abs={ab} / '{tc.get('ep_title', '')}'"
```

- [ ] **Step 2: Verify with unit assertions**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
python -c "
from metrics import extract_metrics
tc = {'season': 2, 'episode': 15, 'absolute': 23, 'language': 'de', 'ep_title': 'Welcome Back'}

# Standard S/E match
m = extract_metrics([{'attributes': {'language': 'de', 'files': [{'file_name': 'Show.S02E15.de.ass'}]}}], tc)
assert m['correct_ep'], m['correct_ep_why']

# Absolute match
m = extract_metrics([{'attributes': {'language': 'de', 'files': [{'file_name': 'Show.S01E23.de.ass'}]}}], tc)
assert m['correct_ep'], m['correct_ep_why']

# Episode title match
m = extract_metrics([{'attributes': {'language': 'de', 'files': [{'file_name': '86.Welcome.Back.de.ass'}]}}], tc)
assert m['correct_ep'], m['correct_ep_why']

# Wrong episode
m = extract_metrics([{'attributes': {'language': 'de', 'files': [{'file_name': 'Show.S01E01.de.ass'}]}}], tc)
assert not m['correct_ep'], 'should not match S01E01'

# Empty
m = extract_metrics([], tc)
assert not m['correct_ep']

print('metrics OK')
"
```

Expected: `metrics OK`

---

## Task 5: runner.py — Matrix Executor

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/runner.py`

- [ ] **Step 1: Write runner.py**

```python
"""Run all strategies × all test cases and return flat results list."""
import time

import requests

from config import get_api_key, OS_BASE_URL, OS_USER_AGENT, TEST_CASES
from strategies import ALL_STRATEGIES
from metrics import extract_metrics

REQUEST_DELAY_S = 0.6   # stay under 40 req/10s free-tier limit


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Api-Key": get_api_key(),
        "User-Agent": OS_USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    return session


def run_matrix(
    test_cases: list[dict] | None = None,
    strategy_fns: list | None = None,
) -> list[dict]:
    if test_cases is None:
        test_cases = TEST_CASES
    if strategy_fns is None:
        strategy_fns = ALL_STRATEGIES

    session = build_session()
    results = []

    for tc in test_cases:
        print(f"\n{'='*65}")
        print(f"{tc['id']} — {tc['series']}")
        print(f"  Sonarr S{tc['season']:02d}E{tc['episode']:02d}  |  abs={tc['absolute']}  |  {tc['note']}")
        print(f"{'='*65}")

        for fn in strategy_fns:
            print(f"  {fn.__name__.replace('strategy_', ''):25s}", end=" ", flush=True)
            try:
                raw = fn(tc, session)
                if raw.get("skipped"):
                    print(f"SKIPPED ({raw.get('skip_reason', '')})")
                    result = {
                        "tc_id": tc["id"], "tc_series": tc["series"],
                        "strategy": raw["strategy"],
                        "result_count": 0, "de_count": 0,
                        "top_filename": "", "correct_ep": False,
                        "correct_ep_why": raw.get("skip_reason", "skipped"),
                        "latency_ms": 0, "api_calls": 0,
                        "params": [], "error": None, "skipped": True,
                        "cascade_winner": None,
                    }
                else:
                    m = extract_metrics(raw["items"], tc)
                    result = {
                        "tc_id": tc["id"], "tc_series": tc["series"],
                        "strategy": raw["strategy"],
                        "result_count": m["result_count"],
                        "de_count": m["de_count"],
                        "top_filename": m["top_filename"],
                        "correct_ep": m["correct_ep"],
                        "correct_ep_why": m["correct_ep_why"],
                        "latency_ms": raw["latency_ms"],
                        "api_calls": raw["api_calls"],
                        "params": raw["params"],
                        "error": None,
                        "skipped": False,
                        "cascade_winner": raw.get("cascade_winner"),
                    }
                    print(
                        f"total={m['result_count']:3d}  "
                        f"de={m['de_count']:2d}  "
                        f"ok={'✓' if m['correct_ep'] else '✗'}  "
                        f"{raw['latency_ms']}ms  "
                        f"calls={raw['api_calls']}"
                        + (f"  [won via {raw['cascade_winner']}]" if raw.get("cascade_winner") else "")
                    )
            except Exception as exc:
                print(f"ERROR: {exc}")
                result = {
                    "tc_id": tc["id"], "tc_series": tc["series"],
                    "strategy": fn.__name__.replace("strategy_", ""),
                    "result_count": 0, "de_count": 0,
                    "top_filename": "", "correct_ep": False,
                    "correct_ep_why": str(exc),
                    "latency_ms": 0, "api_calls": 0,
                    "params": [], "error": str(exc), "skipped": False,
                    "cascade_winner": None,
                }

            results.append(result)
            time.sleep(REQUEST_DELAY_S)

    return results
```

- [ ] **Step 2: Verify**

```bash
python -c "from runner import run_matrix; print('runner OK')"
```

---

## Task 6: report.py — Console Table + Ranking + JSON

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/report.py`

- [ ] **Step 1: Write report.py**

```python
"""Format results: console table, ranked summary, JSON file."""
import json
import os
from datetime import datetime

from tabulate import tabulate


def print_summary_table(results: list[dict]) -> None:
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(r["tc_id"], []).append(r)

    for tc_id, rows in groups.items():
        print(f"\n{'─'*85}")
        print(f"  {tc_id} — {rows[0]['tc_series']}")
        print(f"{'─'*85}")
        table_rows = []
        for r in rows:
            skip_note = " (skip)" if r.get("skipped") else ""
            cascade_note = f" [{r['cascade_winner']}]" if r.get("cascade_winner") else ""
            table_rows.append([
                r["strategy"] + skip_note,
                r["result_count"],
                r["de_count"],
                "✓" if r["correct_ep"] else ("–" if r.get("skipped") else "✗"),
                (r["correct_ep_why"] or "")[:48] + cascade_note,
                f"{r['latency_ms']}ms",
                r["api_calls"],
            ])
        print(tabulate(
            table_rows,
            headers=["Strategy", "Total", "DE", "Ok?", "Detail", "Latency", "Calls"],
            tablefmt="simple",
        ))


def print_recommendations(results: list[dict]) -> None:
    """Score strategies across all non-skipped test cases and print ranked table."""
    scores: dict[str, dict] = {}
    for r in results:
        if r.get("skipped"):
            continue
        s = r["strategy"]
        if s not in scores:
            scores[s] = {
                "strategy": s, "n": 0,
                "cases_with_results": 0, "cases_correct": 0,
                "total_de": 0, "total_calls": 0, "total_ms": 0,
            }
        d = scores[s]
        d["n"] += 1
        if r["result_count"] > 0:
            d["cases_with_results"] += 1
        if r["correct_ep"]:
            d["cases_correct"] += 1
        d["total_de"] += r["de_count"]
        d["total_calls"] += r["api_calls"]
        d["total_ms"] += r["latency_ms"]

    ranked = sorted(
        scores.values(),
        key=lambda d: (
            -d["cases_correct"],
            -d["cases_with_results"],
            -d["total_de"],
            d["total_calls"],
            d["total_ms"],
        ),
    )

    print(f"\n{'═'*85}")
    print("  STRATEGY RANKING")
    print("  Sort: correct-ep hits ↓ → results ↓ → DE count ↓ → API calls ↑ → latency ↑")
    print(f"{'═'*85}")
    rows = [
        [
            f"#{i+1}",
            d["strategy"],
            f"{d['cases_correct']}/{d['n']}",
            f"{d['cases_with_results']}/{d['n']}",
            d["total_de"],
            d["total_calls"],
            f"{d['total_ms']}ms",
        ]
        for i, d in enumerate(ranked)
    ]
    print(tabulate(rows,
        headers=["Rank", "Strategy", "Correct/N", "HasResults/N", "Total DE", "Calls", "Latency"],
        tablefmt="simple",
    ))

    if ranked:
        print(f"\n  WINNER:     {ranked[0]['strategy']}")
    if len(ranked) > 1:
        print(f"  RUNNER-UP:  {ranked[1]['strategy']}")

    # Special cascade breakdown
    cascade_rows = [r for r in results if r["strategy"] == "cascade" and r.get("cascade_winner")]
    if cascade_rows:
        print(f"\n  CASCADE WINNERS per test case:")
        for r in cascade_rows:
            print(f"    {r['tc_id']:5s} → won via {r['cascade_winner']}"
                  f"  ({r['api_calls']} calls, {r['latency_ms']}ms)")


def save_json(results: list[dict], output_dir: str = "results") -> str:
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(output_dir, f"strategy_test_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return path
```

- [ ] **Step 2: Verify**

```bash
python -c "from report import print_summary_table, print_recommendations, save_json; print('report OK')"
```

---

## Task 7: run_test.py — Entry Point

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/run_test.py`

- [ ] **Step 1: Write run_test.py**

```python
"""Entry point — run strategy × test-case matrix.

Usage:
    export OS_API_KEY=<key>
    python run_test.py                          # full matrix
    python run_test.py --tc TC1 TC2             # specific test cases
    python run_test.py --strategy standard abs_fallback cascade
    python run_test.py --tc TC1 --file-path "Z:/Anime/.../episode.mkv"
"""
import argparse
import sys

from config import TEST_CASES
from strategies import ALL_STRATEGIES
from runner import run_matrix
from report import print_summary_table, print_recommendations, save_json


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenSubtitles anime strategy tester")
    p.add_argument("--tc", nargs="*", help="Test case IDs (e.g. TC1 TC3)")
    p.add_argument("--strategy", nargs="*", help="Strategy names (e.g. standard abs_fallback)")
    p.add_argument("--file-path", help="Override file_path for all test cases (enables hash strategy)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    tcs = TEST_CASES
    if args.tc:
        tcs = [tc for tc in TEST_CASES if tc["id"] in args.tc]
        if not tcs:
            print(f"No test cases matched: {args.tc}", file=sys.stderr)
            sys.exit(1)

    if args.file_path:
        tcs = [{**tc, "file_path": args.file_path} for tc in tcs]

    fns = ALL_STRATEGIES
    if args.strategy:
        name_map = {fn.__name__.replace("strategy_", ""): fn for fn in ALL_STRATEGIES}
        fns = [name_map[s] for s in args.strategy if s in name_map]
        missing = [s for s in args.strategy if s not in name_map]
        if missing:
            print(f"Unknown strategies: {missing}\nAvailable: {list(name_map)}", file=sys.stderr)
            sys.exit(1)

    total_expected = len(fns) * len(tcs)
    print(f"Running {len(fns)} strategies × {len(tcs)} test cases = {total_expected} combinations")
    print("(merged=2 API calls, cascade=up to 6; expect ~100 total API calls for full run)")
    print("Delay 0.6s between calls to respect rate limits.\n")

    results = run_matrix(test_cases=tcs, strategy_fns=fns)

    print_summary_table(results)
    print_recommendations(results)

    path = save_json(results)
    print(f"\nResults saved: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify**

```bash
python -c "import run_test; print('entry point OK')"
```

---

## Task 8: test_smoke.py — Offline Unit Tests

**Files:**
- Create: `D:/Sublarr_Projekt/anime_subtitle_test/test_smoke.py`

- [ ] **Step 1: Write test_smoke.py**

```python
"""Offline smoke tests — no API key or network required."""
import os
import unittest
from unittest.mock import MagicMock


def _mock_session(items: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": items}
    s = MagicMock()
    s.get.return_value = resp
    return s


TC = {
    "id": "TC1", "series": "86", "imdb_id": "14950550", "parent_imdb_id": "14950550",
    "season": 2, "episode": 15, "absolute": 23, "ep_title": "Welcome Back",
    "title": "86 EIGHTY-SIX", "language": "de", "file_path": None, "note": "test",
}

ITEM_DE = {"attributes": {"language": "de", "files": [{"file_id": 42, "file_name": "86.S01E23.de.ass"}]}}
ITEM_EN = {"attributes": {"language": "en", "files": [{"file_id": 99, "file_name": "86.S01E23.en.srt"}]}}


class TestConfig(unittest.TestCase):
    def test_all_test_cases_have_required_fields(self):
        from config import TEST_CASES
        required = {"id", "series", "imdb_id", "parent_imdb_id", "season", "episode",
                    "absolute", "ep_title", "title", "language", "file_path"}
        for tc in TEST_CASES:
            missing = required - tc.keys()
            self.assertEqual(missing, set(), f"{tc['id']} missing: {missing}")

    def test_get_api_key_raises_without_env(self):
        from config import get_api_key
        old = os.environ.pop("OS_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError):
                get_api_key()
        finally:
            if old:
                os.environ["OS_API_KEY"] = old


class TestMetrics(unittest.TestCase):
    def test_empty_returns_zeros_and_false(self):
        from metrics import extract_metrics
        m = extract_metrics([], TC)
        self.assertEqual(m["result_count"], 0)
        self.assertFalse(m["correct_ep"])

    def test_standard_se_match(self):
        from metrics import extract_metrics
        item = {"attributes": {"language": "de", "files": [{"file_name": "Show.S02E15.de.ass"}]}}
        m = extract_metrics([item], TC)
        self.assertTrue(m["correct_ep"])

    def test_absolute_as_s1_match(self):
        from metrics import extract_metrics
        item = {"attributes": {"language": "de", "files": [{"file_name": "Show.S01E23.de.ass"}]}}
        m = extract_metrics([item], TC)
        self.assertTrue(m["correct_ep"])

    def test_episode_title_match(self):
        from metrics import extract_metrics
        item = {"attributes": {"language": "de", "files": [{"file_name": "86.Welcome.Back.de.ass"}]}}
        m = extract_metrics([item], TC)
        self.assertTrue(m["correct_ep"])

    def test_wrong_episode_not_matched(self):
        from metrics import extract_metrics
        item = {"attributes": {"language": "de", "files": [{"file_name": "Show.S01E01.de.ass"}]}}
        m = extract_metrics([item], TC)
        self.assertFalse(m["correct_ep"])

    def test_de_count_excludes_other_languages(self):
        from metrics import extract_metrics
        m = extract_metrics([ITEM_DE, ITEM_EN], TC)
        self.assertEqual(m["de_count"], 1)
        self.assertEqual(m["result_count"], 2)


class TestStrategies(unittest.TestCase):
    def _run(self, fn_name: str, items=None) -> dict:
        from strategies import ALL_STRATEGIES
        fn = next(f for f in ALL_STRATEGIES if f.__name__ == f"strategy_{fn_name}")
        session = _mock_session(items or [])
        return fn(TC, session)

    def test_all_strategies_return_required_keys(self):
        from strategies import ALL_STRATEGIES
        required = {"strategy", "items", "latency_ms", "api_calls", "params", "skipped"}
        for fn in ALL_STRATEGIES:
            session = _mock_session([])
            result = fn(TC, session)
            missing = required - result.keys()
            self.assertEqual(missing, set(), f"{fn.__name__} missing keys: {missing}")

    def test_standard_sends_season_and_episode(self):
        r = self._run("standard")
        self.assertEqual(r["strategy"], "standard")
        self.assertEqual(r["params"][0]["season_number"], TC["season"])
        self.assertEqual(r["params"][0]["episode_number"], TC["episode"])

    def test_abs_fallback_uses_season_1_and_absolute(self):
        r = self._run("abs_fallback")
        self.assertEqual(r["params"][0]["season_number"], 1)
        self.assertEqual(r["params"][0]["episode_number"], TC["absolute"])

    def test_hash_skipped_when_no_file_path(self):
        r = self._run("hash")
        self.assertTrue(r["skipped"])

    def test_episode_title_skipped_when_no_title(self):
        from strategies import strategy_episode_title
        tc_no_title = {**TC, "ep_title": ""}
        r = strategy_episode_title(tc_no_title, _mock_session([]))
        self.assertTrue(r["skipped"])

    def test_abs_minus_one_skipped_when_absolute_is_1(self):
        from strategies import strategy_abs_minus_one
        tc_abs1 = {**TC, "absolute": 1}
        r = strategy_abs_minus_one(tc_abs1, _mock_session([]))
        self.assertTrue(r["skipped"])

    def test_merged_deduplicates_same_file_id(self):
        from strategies import strategy_merged
        session = _mock_session([ITEM_DE])
        r = strategy_merged(TC, session)
        self.assertEqual(len(r["items"]), 1)  # both calls return same item
        self.assertEqual(r["api_calls"], 2)

    def test_cascade_stops_at_first_hit(self):
        from strategies import strategy_cascade
        # abs_fallback will be called after hash is skipped (no file_path);
        # mock returns items, so cascade should stop there.
        session = _mock_session([ITEM_DE])
        r = strategy_cascade(TC, session)
        self.assertFalse(r["skipped"])
        self.assertEqual(len(r["items"]), 1)
        # cascade_winner should be the first non-skip strategy that returns items
        self.assertIsNotNone(r.get("cascade_winner"))

    def test_cascade_returns_empty_when_all_fail(self):
        from strategies import strategy_cascade
        session = _mock_session([])  # all strategies return 0
        r = strategy_cascade(TC, session)
        self.assertEqual(r["items"], [])

    def test_abs_plus_one_uses_absolute_plus_1(self):
        r = self._run("abs_plus_one")
        self.assertEqual(r["params"][0]["episode_number"], TC["absolute"] + 1)

    def test_parent_imdb_standard_uses_parent_imdb_id(self):
        r = self._run("parent_imdb_standard")
        self.assertIn("parent_imdb_id", r["params"][0])
        self.assertEqual(r["params"][0]["parent_imdb_id"], TC["parent_imdb_id"])

    def test_imdb_no_lang_has_no_languages_param(self):
        r = self._run("imdb_no_lang")
        self.assertNotIn("languages", r["params"][0])


class TestReport(unittest.TestCase):
    def _sample(self) -> list[dict]:
        return [
            {"tc_id": "TC1", "tc_series": "Test", "strategy": "standard",
             "result_count": 0, "de_count": 0, "top_filename": "", "correct_ep": False,
             "correct_ep_why": "no results", "latency_ms": 100, "api_calls": 1,
             "params": [], "error": None, "skipped": False, "cascade_winner": None},
            {"tc_id": "TC1", "tc_series": "Test", "strategy": "abs_fallback",
             "result_count": 5, "de_count": 3, "top_filename": "Show.S01E23.de.ass",
             "correct_ep": True, "correct_ep_why": "matched abs", "latency_ms": 120,
             "api_calls": 1, "params": [], "error": None, "skipped": False, "cascade_winner": None},
        ]

    def test_save_json_creates_file(self):
        import tempfile
        from report import save_json
        with tempfile.TemporaryDirectory() as tmp:
            path = save_json(self._sample(), output_dir=tmp)
            self.assertTrue(os.path.exists(path))

    def test_print_functions_do_not_raise(self):
        from report import print_summary_table, print_recommendations
        print_summary_table(self._sample())
        print_recommendations(self._sample())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run smoke tests**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
python -m pytest test_smoke.py -v
```

Expected: **all tests pass** (≥20 tests, no network calls).

- [ ] **Step 3: Commit**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
git init && git add .
git commit -m "feat: anime OpenSubtitles strategy test harness — 17 strategies, smoke tests green"
```

---

## Task 9: Live Run

- [ ] **Step 1: Set API key**

```bash
export OS_API_KEY=<paste_from_sublarr_settings>
```

- [ ] **Step 2: Quick sanity — TC1 only, 3 strategies**

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
python run_test.py --tc TC1 --strategy standard abs_fallback cascade
```

Expected: `standard` → 0 results, `abs_fallback` → >0 with German, `cascade` → same hit via abs_fallback.

- [ ] **Step 3: Full matrix**

```bash
python run_test.py
```

Takes ~2 minutes (17 strategies × 5 cases × 0.6s delay, cascade up to 6 sub-calls).

- [ ] **Step 4: If you have a video file, enable hash for TC1**

```bash
python run_test.py --tc TC1 --file-path "Z:/Anime/86 EIGHTY-SIX/S02E15.mkv"
```

- [ ] **Step 5: Inspect the JSON for TC1 detail**

```bash
python -c "
import json, glob
data = json.load(open(sorted(glob.glob('results/*.json'))[-1]))
tc1 = [r for r in data if r['tc_id'] == 'TC1']
for r in sorted(tc1, key=lambda x: -x['result_count']):
    print(f\"{r['strategy']:25s}  total={r['result_count']:3d}  de={r['de_count']:2d}  ok={r['correct_ep']}  {r['top_filename'][:55]}\")
"
```

- [ ] **Step 6: Write FINDINGS.md**

```bash
cat > results/FINDINGS.md << 'EOF'
# Strategy Test Findings — 2026-03-29

## Winner: <fill in>
## Runner-up: <fill in>

## TC1 — 86 EIGHTY-SIX S02E15 (abs 23)
<!-- which strategies returned results? which were correct? -->

## TC2 — Attack on Titan S04E29 (abs 87)
<!-- ... -->

## TC3 — Demon Slayer S03E11 (abs 44)
<!-- ... -->

## TC4 — Vinland Saga S02E24 (abs 48)
<!-- ... -->

## TC5 — One Piece S01E100 (control)
<!-- all strategies should work here -->

## Cascade winner breakdown
<!-- for each TC: which strategy did cascade stop at? -->

## Recommendation for Sublarr opensubtitles.py
<!-- What change (if any) to make based on results -->
EOF
```

---

## Quick Reference

```bash
cd D:/Sublarr_Projekt/anime_subtitle_test
export OS_API_KEY=<key>

python run_test.py                          # full matrix
python run_test.py --tc TC1                # one case, all strategies
python run_test.py --tc TC1 --strategy standard abs_fallback cascade parent_imdb_abs
python run_test.py --tc TC1 --file-path "Z:/path/to/episode.mkv"  # enables hash

# Re-inspect latest results
python -c "
import json,glob
d=json.load(open(sorted(glob.glob('results/*.json'))[-1]))
for r in d:
    if r['tc_id']=='TC1':
        print(f\"{r['strategy']:25s} {r['result_count']:3d} {r['de_count']:2d} {r['correct_ep']}\")
"
```
