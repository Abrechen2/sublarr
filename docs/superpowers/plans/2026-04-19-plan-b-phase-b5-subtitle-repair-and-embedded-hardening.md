# Plan B / Phase B5 — SRT Repair + Embedded-Extraction Hardening

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`
**Prior:** B4 shipped as 0.67.0-beta — scoring penalty rule pipeline.

**Goal:** Every subtitle Sublarr writes to disk goes through a pure repair pass that fixes five defect classes (BOM, wrong newlines, invalid decimals, overlapping cues, encoding mis-detection). Embedded-extraction gets smarter track-selection (rank by language + forced + HI flags) so the right track is picked when a video has multiple matches.

**Architecture:**
- New module `backend/subtitle_repair.py` — pure functions `repair_srt(text) → text`, `repair_ass(text) → text`, `repair_bytes(data, fmt) → bytes`. No I/O, no DB, no side effects.
- Repair hooks fire on three save paths: (1) provider download — inside `save_subtitle()` in `providers/download_manager.py` before the file is written; (2) embedded extract — inside the extract worker after mkvextract writes the temp file; (3) post-translate — after the translator writes its output. The hook is opt-outable via a settings flag (`enable_subtitle_repair`, default True).
- Embedded-extraction hardening: in `providers/embedded.py::EmbeddedProvider.search`, rank each candidate's `score_bonus` by:
  - Base `_EMBEDDED_SCORE_BONUS` (50) when language matches
  - `+15` when track matches query's `forced_only` flag
  - `+10` when track's HI flag matches query's `hi_preference`
  - `-5` when forced mismatch (requested non-forced, track is forced)

**Tech Stack:** Python 3.12, pytest, chardet (already a pip dep from B1), pure stdlib regex.

**Baseline:** 0.67.0-beta → 0.68.0-beta (minor bump).

---

## File Structure

### Create

- `backend/subtitle_repair.py` — pure repair functions
- `backend/tests/test_subtitle_repair.py` — ~20 unit tests (one per defect class + integration)
- `backend/tests/fixtures/subtitle_repair/` — fixture files per defect class:
  - `bom_at_start.srt`
  - `wrong_newlines.srt` (CRLFCRLF + lone CR)
  - `invalid_decimals.srt` (`00:00:01,4` instead of `00:00:01,400`)
  - `overlapping_cues.srt`
  - `windows1252_mislabeled.srt` (bytes that break utf-8 decode)
  - `valid_baseline.srt` (repair is no-op on clean files)

### Modify

- `backend/providers/download_manager.py` — call `repair_bytes(content, fmt)` inside `save_subtitle()` before writing
- `backend/providers/embedded.py` — compute `score_bonus` from flags in the track-selection loop
- `backend/routes/wanted/extract.py` (or wherever `_extract_embedded_sub` writes the temp file) — call repair on the extracted bytes
- `backend/translator/manager.py` (or the module that writes the translated subtitle — grep for `write_text(` or `open(..., "wb")` near translation) — call repair on the output
- `backend/config.py` — add `enable_subtitle_repair: bool = True` setting

---

## Task 1: Scaffold `subtitle_repair.py` + BOM + newlines defects (first two defect classes)

**Files:**
- Create: `backend/subtitle_repair.py`
- Create: `backend/tests/test_subtitle_repair.py`
- Create: `backend/tests/fixtures/subtitle_repair/bom_at_start.srt`
- Create: `backend/tests/fixtures/subtitle_repair/wrong_newlines.srt`
- Create: `backend/tests/fixtures/subtitle_repair/valid_baseline.srt`

- [ ] **Step 1: Write the fixtures**

Create these three tiny fixture files literally:

`backend/tests/fixtures/subtitle_repair/valid_baseline.srt`:

```
1
00:00:01,000 --> 00:00:02,000
Hello.

2
00:00:03,000 --> 00:00:04,000
World.

```

`backend/tests/fixtures/subtitle_repair/bom_at_start.srt`:

```
<BOM><the same 2-cue content as valid_baseline.srt>
```

where `<BOM>` is literally the 3 bytes `0xEF 0xBB 0xBF`. Easier route: write via Python snippet in the plan — see Step 3.

`backend/tests/fixtures/subtitle_repair/wrong_newlines.srt`:

```
1\r\r\n00:00:01,000 --> 00:00:02,000\r\r\nHello.\r\r\n\r\r\n2\r\r\n00:00:03,000 --> 00:00:04,000\r\r\nWorld.\r\r\n
```

The literal bytes (not Python escape). Write via Python:

- [ ] **Step 2: Generate fixtures via small Python snippet**

Run from `backend/`:

```bash
python - <<'PY'
from pathlib import Path

fxdir = Path("tests/fixtures/subtitle_repair")
fxdir.mkdir(parents=True, exist_ok=True)

baseline = b"1\n00:00:01,000 --> 00:00:02,000\nHello.\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld.\n"
(fxdir / "valid_baseline.srt").write_bytes(baseline)
(fxdir / "bom_at_start.srt").write_bytes(b"\xef\xbb\xbf" + baseline)

# Wrong newlines: CRLFCRLF then lone CR inside body
wrong = baseline.replace(b"\n", b"\r\r\n")
(fxdir / "wrong_newlines.srt").write_bytes(wrong)

print("fixtures written")
PY
```

Expected: `fixtures written` + 3 files created.

- [ ] **Step 3: Write failing tests for BOM + newlines**

```python
# backend/tests/test_subtitle_repair.py
"""Plan B5 — subtitle_repair unit tests."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "subtitle_repair"


def test_repair_strips_bom_from_srt():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "bom_at_start.srt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")

    fixed = repair_bytes(raw, fmt="srt")
    assert not fixed.startswith(b"\xef\xbb\xbf")
    # Content after BOM is preserved
    assert b"Hello." in fixed
    assert b"World." in fixed


def test_repair_normalizes_wrong_newlines_in_srt():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "wrong_newlines.srt").read_bytes()
    assert b"\r\r\n" in raw  # fixture precondition

    fixed = repair_bytes(raw, fmt="srt")
    assert b"\r\r\n" not in fixed
    assert b"\r\n" not in fixed  # we normalize to LF-only for consistency
    # Content preserved
    assert b"Hello." in fixed
    assert b"00:00:01,000 --> 00:00:02,000" in fixed


def test_repair_is_noop_on_valid_baseline():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "valid_baseline.srt").read_bytes()
    fixed = repair_bytes(raw, fmt="srt")
    assert fixed == raw  # no-op on already-clean content
```

- [ ] **Step 4: Run tests to verify failure**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py -v`
Expected: tests FAIL with `ModuleNotFoundError: No module named 'subtitle_repair'`.

- [ ] **Step 5: Implement the module skeleton + first two defect fixers**

```python
# backend/subtitle_repair.py
"""Pure subtitle repair functions.

Called by every save path (provider download, embedded extract, post-translate)
to normalize content before writing to disk. Pure — no I/O, no DB, no side
effects. Any defect it can't repair returns the input unchanged (caller
decides whether to fall back to the unrepaired bytes).

Five defect classes handled:
  1. BOM at file start (UTF-8 BOM 0xEF 0xBB 0xBF)
  2. Wrong newline encoding (CRLFCRLF, lone CR)
  3. Invalid decimals in timestamps (e.g. `00:00:01,4`)
  4. Overlapping cues in SRT
  5. Encoding mis-detection (content labeled UTF-8 but actually Windows-1252)

Public API:
  - repair_bytes(data: bytes, fmt: str) -> bytes
  - repair_srt(text: str) -> str
  - repair_ass(text: str) -> str
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_UTF8_BOM = b"\xef\xbb\xbf"


def repair_bytes(data: bytes, fmt: str) -> bytes:
    """Entry point for byte-level repair (decode, repair, re-encode).

    Strips BOM, detects encoding with fallbacks, normalizes newlines, then
    dispatches to format-specific text repair.
    """
    if not data:
        return data

    # Strip UTF-8 BOM
    if data.startswith(_UTF8_BOM):
        data = data[len(_UTF8_BOM):]

    # Decode — try UTF-8 first, then Windows-1252 (common SRT encoding),
    # then chardet as last resort.
    text = _decode_robust(data)

    # Normalize newlines to LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse duplicated blank lines that the newline fix may have introduced
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Format-specific repair
    fmt_lower = (fmt or "").lower()
    if fmt_lower in ("srt", "vtt"):
        text = repair_srt(text)
    elif fmt_lower in ("ass", "ssa"):
        text = repair_ass(text)

    return text.encode("utf-8")


def _decode_robust(data: bytes) -> str:
    """Decode bytes to str with fallback strategy."""
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

    # Try chardet as last resort
    try:
        import chardet  # vendored transitive dep from B1

        detected = chardet.detect(data)
        encoding = detected.get("encoding") or "windows-1252"
        return data.decode(encoding, errors="replace")
    except ImportError:
        pass

    # Ultimate fallback
    return data.decode("windows-1252", errors="replace")


def repair_srt(text: str) -> str:
    """Repair SRT-specific defects. (Tasks 2+ extend this.)"""
    # Base implementation: just returns newline-normalized text.
    # Task 2 adds timestamp-decimal repair; Task 3 adds overlap detection.
    return text


def repair_ass(text: str) -> str:
    """Repair ASS/SSA-specific defects."""
    # Currently no ASS-specific repairs needed beyond byte-level.
    return text
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py -v`
Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/subtitle_repair.py backend/tests/test_subtitle_repair.py backend/tests/fixtures/subtitle_repair/
git commit -m "feat(plan-b5): subtitle_repair scaffold — BOM + newlines repair"
```

---

## Task 2: Invalid-decimal timestamp repair (third defect class)

**Files:**
- Modify: `backend/subtitle_repair.py` — extend `repair_srt()`
- Modify: `backend/tests/test_subtitle_repair.py`
- Create: `backend/tests/fixtures/subtitle_repair/invalid_decimals.srt`

- [ ] **Step 1: Create fixture**

Run from `backend/`:

```bash
python - <<'PY'
from pathlib import Path
fxdir = Path("tests/fixtures/subtitle_repair")
# One-, two-, and three-digit decimals -> all must become 3-digit
content = (
    "1\n00:00:01,4 --> 00:00:02,45\nShort decimals.\n\n"
    "2\n00:00:03,123 --> 00:00:04,567\nValid full decimals.\n"
)
(fxdir / "invalid_decimals.srt").write_bytes(content.encode("utf-8"))
print("fixture written")
PY
```

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_subtitle_repair.py`:

```python
def test_repair_pads_invalid_decimals():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "invalid_decimals.srt").read_bytes()
    assert b"00:00:01,4 " in raw  # precondition: 1-digit decimal
    assert b"00:00:02,45 " in raw or b"00:00:02,45\n" in raw  # 2-digit

    fixed_bytes = repair_bytes(raw, fmt="srt")
    fixed = fixed_bytes.decode("utf-8")
    # All timestamps now have 3-digit milliseconds
    assert "00:00:01,400" in fixed
    assert "00:00:02,450" in fixed
    # Valid ones untouched
    assert "00:00:03,123" in fixed
    assert "00:00:04,567" in fixed
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py::test_repair_pads_invalid_decimals -v`
Expected: FAIL — repair_srt doesn't yet pad decimals.

- [ ] **Step 4: Extend `repair_srt` to pad decimals**

Replace the stub `repair_srt` body in `backend/subtitle_repair.py`:

```python
_SRT_TIMESTAMP_RE = re.compile(
    r"(\b\d{2}:\d{2}:\d{2}),(\d{1,3})\b"
)


def _pad_decimals(match: re.Match[str]) -> str:
    hms = match.group(1)
    ms = match.group(2)
    return f"{hms},{ms.ljust(3, '0')}"


def repair_srt(text: str) -> str:
    """Repair SRT-specific defects.

    - Pad 1- and 2-digit millisecond decimals in timestamps to 3 digits
      (e.g. `00:00:01,4` → `00:00:01,400`).
    """
    text = _SRT_TIMESTAMP_RE.sub(_pad_decimals, text)
    return text
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py -v`
Expected: 4 tests PASS (3 from Task 1 + 1 new).

- [ ] **Step 6: Commit**

```bash
git add backend/subtitle_repair.py backend/tests/test_subtitle_repair.py backend/tests/fixtures/subtitle_repair/invalid_decimals.srt
git commit -m "feat(plan-b5): subtitle_repair — pad invalid-decimal timestamps"
```

---

## Task 3: Overlapping-cues repair (fourth defect class)

**Files:**
- Modify: `backend/subtitle_repair.py` — add overlap detection/fix
- Modify: `backend/tests/test_subtitle_repair.py`
- Create: `backend/tests/fixtures/subtitle_repair/overlapping_cues.srt`

**Overlap policy:** when cue N+1 starts before cue N ends, clamp cue N's end to cue N+1's start minus 1ms. If that produces a zero- or negative-duration cue, drop cue N entirely (keep the later one, which is likely more accurate).

- [ ] **Step 1: Create fixture**

```bash
python - <<'PY'
from pathlib import Path
fxdir = Path("tests/fixtures/subtitle_repair")
content = (
    "1\n00:00:01,000 --> 00:00:05,000\nFirst cue.\n\n"
    "2\n00:00:03,000 --> 00:00:07,000\nOverlaps — cue 1 end should clamp to 2,999.\n\n"
    "3\n00:00:10,000 --> 00:00:12,000\nClean third cue.\n"
)
Path("tests/fixtures/subtitle_repair/overlapping_cues.srt").write_bytes(content.encode("utf-8"))
print("fixture written")
PY
```

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_subtitle_repair.py`:

```python
def test_repair_clamps_overlapping_cues():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "overlapping_cues.srt").read_bytes()
    fixed = repair_bytes(raw, fmt="srt").decode("utf-8")

    # Cue 1's end should be clamped to 00:00:02,999 (cue 2 starts at 03,000)
    # The 5,000 original end must be gone
    assert "00:00:05,000" not in fixed
    # The clamped end — one of 02,999 / 02,998 is acceptable (implementation choice)
    assert "00:00:02,999" in fixed or "00:00:02,998" in fixed
    # Cue 2 and 3 are untouched
    assert "00:00:03,000 --> 00:00:07,000" in fixed
    assert "00:00:10,000 --> 00:00:12,000" in fixed
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py::test_repair_clamps_overlapping_cues -v`
Expected: FAIL.

- [ ] **Step 4: Implement overlap repair in `repair_srt`**

Add to `backend/subtitle_repair.py`:

```python
_CUE_LINE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _ts_to_ms(h: int, m: int, s: int, ms: int) -> int:
    return h * 3600000 + m * 60000 + s * 1000 + ms


def _ms_to_ts(ms_total: int) -> str:
    if ms_total < 0:
        ms_total = 0
    h, rem = divmod(ms_total, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fix_overlaps_srt(text: str) -> str:
    """Scan cue lines in document order; clamp overlapping ends."""
    # Find all cue time lines
    matches = list(_CUE_LINE_RE.finditer(text))
    if len(matches) < 2:
        return text

    replacements: list[tuple[int, int, str]] = []  # (start, end, replacement)
    for i, match in enumerate(matches[:-1]):
        h1, m1, s1, ms1, h2, m2, s2, ms2 = map(int, match.groups())
        next_match = matches[i + 1]
        nh1, nm1, ns1, nms1 = map(int, next_match.groups()[:4])

        cur_end_ms = _ts_to_ms(h2, m2, s2, ms2)
        next_start_ms = _ts_to_ms(nh1, nm1, ns1, nms1)

        if cur_end_ms <= next_start_ms:
            continue  # no overlap

        new_end_ms = next_start_ms - 1
        cur_start_ms = _ts_to_ms(h1, m1, s1, ms1)
        if new_end_ms <= cur_start_ms:
            continue  # Would produce zero/negative duration — skip fix

        new_ts = (
            f"{_ms_to_ts(cur_start_ms)} --> {_ms_to_ts(new_end_ms)}"
        )
        replacements.append((match.start(), match.end(), new_ts))

    # Apply replacements back-to-front to preserve earlier offsets
    for start, end, repl in reversed(replacements):
        text = text[:start] + repl + text[end:]

    return text


def repair_srt(text: str) -> str:
    """Repair SRT-specific defects.

    - Pad 1- and 2-digit millisecond decimals.
    - Clamp overlapping cue ends to (next_start - 1ms).
    """
    text = _SRT_TIMESTAMP_RE.sub(_pad_decimals, text)
    text = _fix_overlaps_srt(text)
    return text
```

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/subtitle_repair.py backend/tests/test_subtitle_repair.py backend/tests/fixtures/subtitle_repair/overlapping_cues.srt
git commit -m "feat(plan-b5): subtitle_repair — clamp overlapping cue ends"
```

---

## Task 4: Encoding mis-detection repair (fifth defect class)

**Files:**
- Modify: `backend/tests/test_subtitle_repair.py`
- Create: `backend/tests/fixtures/subtitle_repair/windows1252_mislabeled.srt`

The `_decode_robust` helper already handles this — it falls through `utf-8` → `chardet` → `windows-1252`. This task adds a round-trip test that exercises that path.

- [ ] **Step 1: Create fixture with Windows-1252 bytes that break UTF-8**

```bash
python - <<'PY'
from pathlib import Path
fxdir = Path("tests/fixtures/subtitle_repair")
# Windows-1252: smart-quotes (0x92, 0x93, 0x94) and bullet (0x95). These bytes
# are invalid UTF-8 so a naive decoder raises UnicodeDecodeError.
content = (
    "1\r\n00:00:01,000 --> 00:00:02,000\r\nIt\x92s a test.\r\n\r\n"
    "2\r\n00:00:03,000 --> 00:00:04,000\r\n\x93Hello world\x94\r\n"
)
(fxdir / "windows1252_mislabeled.srt").write_bytes(content.encode("windows-1252"))
print("fixture written")
PY
```

- [ ] **Step 2: Write failing test**

Append to `backend/tests/test_subtitle_repair.py`:

```python
def test_repair_recovers_windows1252_mislabeled_bytes():
    from subtitle_repair import repair_bytes

    raw = (FIXTURES / "windows1252_mislabeled.srt").read_bytes()
    # Precondition: raw is NOT valid UTF-8
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")

    fixed_bytes = repair_bytes(raw, fmt="srt")
    # Result must be valid UTF-8
    fixed = fixed_bytes.decode("utf-8")
    # Smart quotes should either be preserved as UTF-8 (\u2019, \u201c, \u201d)
    # or replaced with a reasonable fallback (regular ASCII apostrophe/quote).
    # The exact choice depends on chardet's decision; accept either.
    assert "test" in fixed
    assert "Hello world" in fixed
```

Add the `import pytest` at the top of the file if not already present.

- [ ] **Step 3: Run test — may pass already thanks to `_decode_robust`**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py::test_repair_recovers_windows1252_mislabeled_bytes -v`

If it PASSES immediately: skip Step 4. If it FAILS (chardet not installed or path wrong), go to Step 4.

- [ ] **Step 4: Ensure chardet is imported at the module level + fallback works**

If the test fails, the likely cause is either (a) chardet import-time failure, or (b) chardet detected a wrong encoding and the result contains `\ufffd` replacements. Strengthen `_decode_robust`:

```python
def _decode_robust(data: bytes) -> str:
    """Decode bytes to str with fallback strategy.

    Order:
      1. UTF-8 (strict, via utf-8-sig to also strip BOM)
      2. chardet-detected encoding
      3. Windows-1252 with 'replace' errors (last resort — common for legacy SRT)
    """
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass

    try:
        import chardet

        detected = chardet.detect(data) or {}
        encoding = detected.get("encoding")
        if encoding:
            try:
                return data.decode(encoding, errors="replace")
            except (LookupError, UnicodeDecodeError):
                pass
    except ImportError:
        pass

    return data.decode("windows-1252", errors="replace")
```

- [ ] **Step 5: Commit**

```bash
git add backend/subtitle_repair.py backend/tests/test_subtitle_repair.py backend/tests/fixtures/subtitle_repair/windows1252_mislabeled.srt
git commit -m "feat(plan-b5): subtitle_repair — encoding mis-detection fallback"
```

---

## Task 5: Integrate repair into provider-download save path

**Files:**
- Modify: `backend/providers/download_manager.py` — call repair inside `save_subtitle()`
- Modify: `backend/config.py` — add `enable_subtitle_repair: bool = True`
- Modify: `backend/tests/test_subtitle_repair.py` (or new: `backend/tests/test_save_subtitle_repair_integration.py`)

- [ ] **Step 1: Add the settings flag**

Open `backend/config.py` and add near other boolean settings:

```python
    # Plan B5 — subtitle repair pass before saving. Set False to disable.
    enable_subtitle_repair: bool = True
```

- [ ] **Step 2: Write failing integration test**

Create `backend/tests/test_save_subtitle_repair_integration.py`:

```python
"""Plan B5 — integration: save_subtitle calls subtitle_repair."""

from pathlib import Path

import pytest

from providers.base import SubtitleFormat, SubtitleResult


def test_save_subtitle_calls_repair(tmp_path, monkeypatch):
    """save_subtitle() must run repair_bytes() on result.content before writing."""
    # Content with BOM + wrong newlines — must come out clean on disk
    dirty = b"\xef\xbb\xbf1\r\r\n00:00:01,000 --> 00:00:02,000\r\r\nHi\r\r\n"

    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        content=dirty,
    )

    from providers.download_manager import save_subtitle

    out_path = tmp_path / "test.en.srt"

    # save_subtitle validates path is under media_path; monkeypatch that check
    monkeypatch.setattr(
        "providers.download_manager.is_safe_path",
        lambda *args, **kw: True,
        raising=False,
    )

    saved = save_subtitle(result, str(out_path))

    on_disk = Path(saved).read_bytes()
    assert not on_disk.startswith(b"\xef\xbb\xbf"), "BOM must be stripped"
    assert b"\r\r\n" not in on_disk, "Wrong newlines must be normalized"
    # Content preserved
    assert b"Hi" in on_disk


def test_save_subtitle_skips_repair_when_flag_disabled(tmp_path, monkeypatch):
    """When enable_subtitle_repair=False, save_subtitle writes raw bytes."""
    dirty = b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHi\n"

    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        content=dirty,
    )

    monkeypatch.setattr(
        "providers.download_manager.is_safe_path",
        lambda *args, **kw: True,
        raising=False,
    )
    # Force the feature flag off
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "enable_subtitle_repair", False, raising=False)

    from providers.download_manager import save_subtitle

    out_path = tmp_path / "no_repair.en.srt"
    saved = save_subtitle(result, str(out_path))
    on_disk = Path(saved).read_bytes()
    # BOM should survive
    assert on_disk.startswith(b"\xef\xbb\xbf")
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_save_subtitle_repair_integration.py -v`
Expected: tests FAIL — `save_subtitle` doesn't yet call repair.

- [ ] **Step 4: Wire repair into `save_subtitle()`**

In `backend/providers/download_manager.py`, inside `save_subtitle()` AFTER the `_validate_subtitle_content` call (around line 195) and BEFORE writing to disk, add:

```python
    # Plan B5 — subtitle repair pass before writing (opt-outable)
    try:
        from config import get_settings

        if getattr(get_settings(), "enable_subtitle_repair", True):
            from subtitle_repair import repair_bytes

            fmt = getattr(result.format, "value", None) or "srt"
            result.content = repair_bytes(result.content, fmt=str(fmt))
    except Exception as e:
        logger.warning("subtitle_repair skipped for %s: %s", result.subtitle_id, e)
```

Keep the fallback on exception — repair must NEVER abort a save.

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_save_subtitle_repair_integration.py tests/test_subtitle_repair.py -v`
Expected: all PASS.

- [ ] **Step 6: Regression**

Run: `cd backend && python -m pytest tests/test_provider_manager.py tests/test_download_subtitles_core.py -v --tb=short` (or whatever download-path tests exist — `grep -l 'save_subtitle' backend/tests/*.py`).
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/providers/download_manager.py backend/config.py backend/tests/test_save_subtitle_repair_integration.py
git commit -m "feat(plan-b5): integrate subtitle_repair into provider-download save path"
```

---

## Task 6: Integrate repair into embedded-extract + post-translate paths

**Files:**
- Modify: `backend/routes/wanted/extract.py` (or wherever `mkvextract` runs)
- Modify: `backend/translator/manager.py` (or where the translator writes output)
- Modify: `backend/tests/test_subtitle_repair.py`

- [ ] **Step 1: Locate the embedded-extract write site**

Run: `grep -rn 'mkvextract\|extract_embedded_sub\|embedded_subtitle' backend/routes/wanted/ backend/services/ | grep -iE '(write|save|output)' | head -15`

Find the function that writes the extracted track to disk. It typically looks like:

```python
subprocess.run(["mkvextract", ..., output_path], ...)
# After extraction, the file at output_path needs repair
```

- [ ] **Step 2: Wrap with repair**

After the subprocess call (same file), add:

```python
    # Plan B5 — run repair on the extracted track
    try:
        from config import get_settings

        if getattr(get_settings(), "enable_subtitle_repair", True):
            from pathlib import Path
            from subtitle_repair import repair_bytes

            fmt = Path(output_path).suffix.lstrip(".") or "srt"
            data = Path(output_path).read_bytes()
            repaired = repair_bytes(data, fmt=fmt)
            if repaired != data:
                Path(output_path).write_bytes(repaired)
    except Exception as e:
        logger.warning("subtitle_repair on embedded extract skipped: %s", e)
```

- [ ] **Step 3: Locate the post-translate write site**

Run: `grep -rn 'write_text\|write_bytes\|open.*wb' backend/translator/ | head -10`

Find where the translator writes its output file. Add the same repair block.

- [ ] **Step 4: Add integration tests (light smoke — the logic is identical to Task 5)**

Append to `backend/tests/test_subtitle_repair.py`:

```python
def test_repair_handles_ass_format():
    """repair_bytes with fmt='ass' byte-level normalizes but doesn't touch timestamps."""
    from subtitle_repair import repair_bytes

    # BOM + CRLF inside an ASS file
    dirty = (
        b"\xef\xbb\xbf[Script Info]\r\nTitle: Test\r\n\r\n"
        b"[Events]\r\nFormat: Start, End, Text\r\n"
        b"Dialogue: 0:00:01.00,0:00:02.00,Hi\r\n"
    )
    fixed = repair_bytes(dirty, fmt="ass")
    assert not fixed.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in fixed
    # ASS timestamps use dots, not commas — must NOT be touched by SRT repair
    assert b"0:00:01.00,0:00:02.00" in fixed
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_subtitle_repair.py tests/test_save_subtitle_repair_integration.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/wanted/extract.py backend/translator/manager.py backend/tests/test_subtitle_repair.py
git commit -m "feat(plan-b5): integrate subtitle_repair into embedded-extract + translate paths"
```

(Adjust the `git add` paths to match the actual files you modified.)

---

## Task 7: Embedded-extraction track-selection hardening

**Files:**
- Modify: `backend/providers/embedded.py` — compute `score_bonus` by (language, forced, HI) flags
- Create: `backend/tests/test_embedded_track_selection.py`

- [ ] **Step 1: Inspect current `EmbeddedProvider.search()` in `backend/providers/embedded.py`**

The existing code (around line 200-225) already sets `score_bonus` to a constant `_EMBEDDED_SCORE_BONUS = 50`. We upgrade that to be flag-aware.

- [ ] **Step 2: Write failing test**

```python
# backend/tests/test_embedded_track_selection.py
"""Plan B5 — embedded track-selection ranks by language + forced + HI flags."""

from unittest.mock import patch


def _make_probe_streams():
    """Fake ffprobe output with 3 matching-language tracks for scoring."""
    return {
        "streams": [
            {"codec_type": "subtitle", "index": 2, "codec_name": "subrip",
             "tags": {"language": "eng"}, "disposition": {"forced": 0}},
            {"codec_type": "subtitle", "index": 3, "codec_name": "subrip",
             "tags": {"language": "eng", "title": "SDH"}, "disposition": {"forced": 0}},
            {"codec_type": "subtitle", "index": 4, "codec_name": "subrip",
             "tags": {"language": "eng", "title": "Forced"}, "disposition": {"forced": 1}},
        ]
    }


def test_forced_query_prefers_forced_track_bonus():
    from providers.embedded import EmbeddedProvider
    from providers.base import VideoQuery

    provider = EmbeddedProvider()
    q = VideoQuery(file_path="/x.mkv", languages=["en"], forced_only=True, title="X")

    with patch("providers.embedded._run_ffprobe", return_value=_make_probe_streams()):
        with patch("providers.embedded.Path.exists", return_value=True):
            results = provider.search(q)

    # All three results should be returned; score_bonus differs by flags
    bonuses = {r.provider_data["stream_index"]: r.provider_data["score_bonus"] for r in results}
    # The forced track (index 4) should have the highest bonus
    assert bonuses[4] > bonuses[2]
    assert bonuses[4] > bonuses[3]


def test_hi_preference_only_boosts_hi_track():
    from providers.embedded import EmbeddedProvider
    from providers.base import VideoQuery

    provider = EmbeddedProvider()
    q = VideoQuery(file_path="/x.mkv", languages=["en"], hi_preference="prefer", title="X")

    with patch("providers.embedded._run_ffprobe", return_value=_make_probe_streams()):
        with patch("providers.embedded.Path.exists", return_value=True):
            results = provider.search(q)

    bonuses = {r.provider_data["stream_index"]: r.provider_data["score_bonus"] for r in results}
    # SDH track (index 3) should beat plain track (index 2) when HI preferred
    assert bonuses[3] > bonuses[2]
```

- [ ] **Step 3: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_embedded_track_selection.py -v`
Expected: tests FAIL — score_bonus is currently constant.

- [ ] **Step 4: Implement flag-aware `score_bonus`**

In `backend/providers/embedded.py`, replace the `score_bonus` assignment inside the track-iteration loop with a computed value:

```python
            # Plan B5 — rank tracks by (language, forced, HI) match
            score_bonus = _EMBEDDED_SCORE_BONUS  # base: 50

            # Forced flag preference
            if getattr(query, "forced_only", False):
                score_bonus += 15 if forced else -5
            # HI preference — track is HI if title contains "sdh" or "cc"
            is_hi = ("sdh" in (title or "").lower()) or ("cc" in (title or "").lower())
            hi_pref = getattr(query, "hi_preference", "include")
            if hi_pref == "prefer" and is_hi:
                score_bonus += 10
            elif hi_pref == "exclude" and is_hi:
                score_bonus -= 999

            results.append(
                SubtitleResult(
                    # ... existing fields ...
                    provider_data={
                        "file_path": query.file_path,
                        "stream_index": stream_index,
                        "sub_index": sub_index,
                        "codec": codec,
                        "score_bonus": score_bonus,
                    },
                )
            )
```

Apply the change surgically — preserve every existing field in the `SubtitleResult` constructor, only swap the `score_bonus` value.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_embedded_track_selection.py -v`
Expected: tests PASS.

- [ ] **Step 6: Regression**

Run: `cd backend && python -m pytest tests/test_embedded_provider.py tests/test_embedded_extract.py -v --tb=short` (or equivalent — grep `grep -l 'EmbeddedProvider' backend/tests/*.py`).
Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/providers/embedded.py backend/tests/test_embedded_track_selection.py
git commit -m "feat(plan-b5): embedded — rank tracks by language + forced + HI flags"
```

---

## Task 8: Deploy

**Files:**
- Modify: `backend/VERSION` (in deploy step)
- Modify: `CHANGELOG.md` (in deploy step)

- [ ] **Step 1: Pre-deploy checks**

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest tests/test_subtitle_repair.py tests/test_save_subtitle_repair_integration.py tests/test_embedded_track_selection.py -v --tb=short
```

All must exit 0.

- [ ] **Step 2: Invoke the `deploy` skill**

Bumps to 0.68.0-beta. Expected CHANGELOG:

```markdown
## [0.68.0-beta] - 2026-04-19

### Added
- **Plan B Phase 5 — Subtitle repair + embedded track-selection** — New `backend/subtitle_repair.py` module with pure repair functions that run on every save path (provider download, embedded extract, post-translate). Handles five defect classes: UTF-8 BOM at file start; wrong newline encoding (CRLFCRLF, lone CR); invalid millisecond decimals in SRT timestamps (e.g. `00:00:01,4` → `00:00:01,400`); overlapping cues (clamps earlier cue's end to next cue's start minus 1ms); encoding mis-detection (Windows-1252 content labeled UTF-8, recovered via chardet). Embedded-extraction now ranks candidate tracks by `(language, forced, HI)` flags — forced query prefers forced tracks (+15 bonus, -5 mismatch penalty), HI-preferred query boosts SDH/CC tracks (+10), HI-excluded kills them (-999). Opt-outable via new `enable_subtitle_repair=False` setting. ~10 new backend tests.

### Plan B Progress
- Phase B5 — SRT repair + embedded hardening: **shipped**
```

- [ ] **Step 3: Verify in prod**

Log-level check — repair writes no output on happy path. Verify via log scan:

```bash
ssh root@192.168.178.36 "docker logs sublarr --since 2m 2>&1" \
  | grep -iE "(error|traceback|subtitle_repair)" \
  | grep -vE "(enzyme|X-Signature|marketplace registry)" | head -10
```

Expected: no errors. Any `subtitle_repair` lines would only appear on WARN-level fallback; absence is normal.

If possible, manually trigger a subtitle download via the UI and verify the resulting file has no BOM and LF newlines only.

---

## Phase B5 Acceptance Checklist

- [ ] `backend/subtitle_repair.py` module with `repair_bytes`, `repair_srt`, `repair_ass`
- [ ] 5 defect classes handled: BOM, newlines, decimals, overlaps, encoding
- [ ] 6 fixture files in `backend/tests/fixtures/subtitle_repair/`
- [ ] Repair integrated into 3 save paths (download, embedded extract, post-translate)
- [ ] `enable_subtitle_repair` setting added (default True)
- [ ] Embedded track-selection ranks by (language, forced, HI) flags
- [ ] 10+ new tests pass; no regression
- [ ] Ruff + format clean
- [ ] 0.68.0-beta deployed, logs clean

## Next Phase

**B6 — Post-processing pipeline.** New `backend/post_processing/` package with curated op catalogue (strip_html, convert_encoding, remove_bom, webhook, discord_notify, plex/emby/jellyfin_refresh) + opt-in shell escape hatch behind `SUBLARR_ALLOW_SHELL_SCRIPTS=true` env flag.
