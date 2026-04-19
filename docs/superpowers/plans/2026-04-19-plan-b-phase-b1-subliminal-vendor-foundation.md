# Plan B / Phase B1 — Subliminal Vendor Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-19-plan-b-subtitle-delivery-quality-design.md`

**Goal:** Vendor Subliminal 2.2.0 + babelfish into `backend/providers/_vendor/`, build `SubliminalProviderAdapter` shim, wire ONE pilot provider (`opensubtitles_subliminal`) end-to-end.

**Architecture:** Subliminal + babelfish copied into `backend/providers/_vendor/`. A sys.path shim in `_vendor/__init__.py` makes `import subliminal` and `import babelfish` work transparently. Other transitive deps (`pysrt`, `dogpile.cache`, `stevedore`, `chardet`) come from pip. `SubliminalProviderAdapter(SubtitleProvider)` wraps any Subliminal `Provider` class, converting Sublarr's `VideoQuery ↔ subliminal.Video` and `subliminal.Subtitle → SubtitleResult`. Pilot: Subliminal's OpenSubtitles XML-RPC provider registered as `opensubtitles_subliminal` (distinct from Sublarr's native `opensubtitles_fetch`).

**Tech Stack:** Python 3.12, pytest, Subliminal 2.2.0 (MIT license, vendored), babelfish 0.6.1 (BSD, vendored), dogpile.cache + stevedore + pysrt (pip deps).

**Baseline:** 0.63.0-beta → 0.64.0-beta (minor bump, first phase of Plan B).

---

## File Structure

### Create

- `backend/providers/_vendor/__init__.py` — sys.path shim
- `backend/providers/_vendor/subliminal/` — vendored Subliminal 2.2.0 source tree
- `backend/providers/_vendor/babelfish/` — vendored babelfish 0.6.1 source tree
- `backend/providers/_vendor/LICENSE_subliminal` — Subliminal MIT license
- `backend/providers/_vendor/LICENSE_babelfish` — babelfish BSD license
- `backend/providers/_vendor/VENDOR_PATCHES.md` — source commit SHAs + applied patches ledger
- `backend/providers/subliminal_adapter.py` — `SubliminalProviderAdapter` class
- `backend/providers/subliminal_opensubtitles.py` — pilot wrapper that registers `opensubtitles_subliminal`
- `backend/tests/test_subliminal_vendor.py` — vendored-import smoke tests
- `backend/tests/test_subliminal_adapter.py` — adapter unit tests
- `backend/tests/test_subliminal_opensubtitles_pilot.py` — pilot provider integration test

### Modify

- `backend/requirements.txt` — add `dogpile.cache`, `stevedore`, `pysrt`, `chardet` (if missing)
- `backend/providers/registry.py` — add `"opensubtitles_subliminal"` to `_BUILTIN_PROVIDERS`
- `backend/VERSION` — 0.63.0-beta → 0.64.0-beta (in deploy task)
- `CHANGELOG.md` — new section (in deploy task)

---

## Task 1: Scaffold vendor directory + sys.path shim

**Files:**
- Create: `backend/providers/_vendor/__init__.py`
- Test: `backend/tests/test_subliminal_vendor.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_subliminal_vendor.py
"""Smoke tests for the vendored Subliminal + babelfish packages."""

import sys
from pathlib import Path


def test_vendor_directory_added_to_sys_path():
    """Importing providers._vendor must inject the vendor dir into sys.path."""
    import providers._vendor  # noqa: F401  (side-effect import)

    vendor_dir = str(Path(providers._vendor.__file__).parent)
    assert vendor_dir in sys.path, (
        f"Expected {vendor_dir} in sys.path after import; got {sys.path[:5]}..."
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_subliminal_vendor.py::test_vendor_directory_added_to_sys_path -v`
Expected: `FAIL` with `ModuleNotFoundError: No module named 'providers._vendor'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/providers/_vendor/__init__.py
"""Vendored third-party libraries for Sublarr.

At import time this package inserts its own directory into sys.path[0] so
that the sibling packages (e.g. subliminal/, babelfish/) are importable as
top-level modules — the same pattern Bazarr uses for its libs/ directory.

Vendored packages live alongside this file, one directory per package.
See VENDOR_PATCHES.md for source commit SHAs and applied patches.
"""

import os
import sys

_VENDOR_DIR = os.path.dirname(os.path.abspath(__file__))
if _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_subliminal_vendor.py::test_vendor_directory_added_to_sys_path -v`
Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add backend/providers/_vendor/__init__.py backend/tests/test_subliminal_vendor.py
git commit -m "feat(plan-b1): scaffold _vendor/ dir with sys.path shim"
```

---

## Task 2: Add transitive pip dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add Subliminal transitive deps to requirements**

Open `backend/requirements.txt` and add these lines in alphabetical position:

```
chardet>=5.2.0
dogpile.cache>=1.3.0
pysrt>=1.1.2
stevedore>=5.2.0
```

(Skip any that already exist — `grep -E "^(chardet|dogpile|pysrt|stevedore)" backend/requirements.txt` first; add only the missing ones.)

- [ ] **Step 2: Install the new deps locally**

Run: `cd backend && pip install -r requirements.txt`
Expected: `Successfully installed ...` for the new packages.

- [ ] **Step 3: Verify imports**

Run: `cd backend && python -c "import chardet, dogpile.cache, pysrt, stevedore; print('all ok')"`
Expected: `all ok`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(plan-b1): add Subliminal transitive deps to requirements"
```

---

## Task 3: Vendor Subliminal 2.2.0 source tree

**Files:**
- Create: `backend/providers/_vendor/subliminal/` (~40 files)
- Create: `backend/providers/_vendor/LICENSE_subliminal`
- Create: `backend/providers/_vendor/VENDOR_PATCHES.md`

- [ ] **Step 1: Clone Subliminal at the target tag**

Run (outside the repo, e.g. in `/tmp`):

```bash
cd /tmp && rm -rf subliminal_src && git clone https://github.com/Diaoul/subliminal.git subliminal_src
cd subliminal_src && git checkout v2.2.0
git rev-parse HEAD   # record for VENDOR_PATCHES.md
```

Expected: clone succeeds, git checkout prints something like `HEAD is now at abcdef1 ...`.

- [ ] **Step 2: Copy the subliminal package into the vendor directory**

```bash
cp -r /tmp/subliminal_src/subliminal/ D:/Sublarr_Projekt/Sublarr/backend/providers/_vendor/subliminal/
cp /tmp/subliminal_src/LICENSE D:/Sublarr_Projekt/Sublarr/backend/providers/_vendor/LICENSE_subliminal
```

Expected: `backend/providers/_vendor/subliminal/__init__.py` + all Subliminal modules present.

- [ ] **Step 3: Create VENDOR_PATCHES.md ledger**

```markdown
# Vendored Package Patches Ledger

This file tracks the provenance of vendored libraries in this directory
and any patches applied after import.

## subliminal

- **Source:** https://github.com/Diaoul/subliminal
- **Version:** 2.2.0
- **Commit:** <paste the SHA printed by `git rev-parse HEAD` in Task 3 Step 1>
- **License:** MIT (see `LICENSE_subliminal`)
- **Patches applied:** none

## babelfish

- **Source:** https://github.com/Diaoul/babelfish
- **Version:** 0.6.1
- **Commit:** <fill in during Task 4>
- **License:** BSD-3-Clause (see `LICENSE_babelfish`)
- **Patches applied:** none
```

Write this to `backend/providers/_vendor/VENDOR_PATCHES.md` — replacing `<paste the SHA...>` with the actual commit SHA.

- [ ] **Step 4: Add vendored-import smoke test**

Append to `backend/tests/test_subliminal_vendor.py`:

```python
def test_vendored_subliminal_importable():
    """The vendored Subliminal must be importable as a top-level package."""
    import providers._vendor  # noqa: F401  (trigger sys.path shim)

    import subliminal

    assert hasattr(subliminal, "__version__"), "subliminal.__version__ attribute missing"
    assert subliminal.__version__.startswith("2.2"), (
        f"Expected Subliminal 2.2.x, got {subliminal.__version__}"
    )


def test_vendored_subliminal_providers_discoverable():
    """Subliminal's provider entry points must be discoverable via stevedore."""
    import providers._vendor  # noqa: F401

    from subliminal.providers import Provider  # base class

    assert Provider is not None, "subliminal.providers.Provider not importable"
```

- [ ] **Step 5: Run the new tests**

Run: `cd backend && python -m pytest tests/test_subliminal_vendor.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/providers/_vendor/subliminal backend/providers/_vendor/LICENSE_subliminal backend/providers/_vendor/VENDOR_PATCHES.md backend/tests/test_subliminal_vendor.py
git commit -m "feat(plan-b1): vendor Subliminal 2.2.0 source tree"
```

---

## Task 4: Vendor babelfish 0.6.1

**Files:**
- Create: `backend/providers/_vendor/babelfish/`
- Create: `backend/providers/_vendor/LICENSE_babelfish`
- Modify: `backend/providers/_vendor/VENDOR_PATCHES.md`
- Modify: `backend/tests/test_subliminal_vendor.py`

- [ ] **Step 1: Clone babelfish at target tag**

```bash
cd /tmp && rm -rf babelfish_src && git clone https://github.com/Diaoul/babelfish.git babelfish_src
cd babelfish_src && git checkout v0.6.1
git rev-parse HEAD   # record for VENDOR_PATCHES.md
```

- [ ] **Step 2: Copy package + LICENSE**

```bash
cp -r /tmp/babelfish_src/babelfish/ D:/Sublarr_Projekt/Sublarr/backend/providers/_vendor/babelfish/
cp /tmp/babelfish_src/LICENSE D:/Sublarr_Projekt/Sublarr/backend/providers/_vendor/LICENSE_babelfish
```

- [ ] **Step 3: Fill in the babelfish SHA in VENDOR_PATCHES.md**

Edit the `## babelfish` section and replace the `<fill in>` placeholder with the actual commit SHA from Step 1.

- [ ] **Step 4: Add babelfish smoke test**

Append to `backend/tests/test_subliminal_vendor.py`:

```python
def test_vendored_babelfish_importable():
    """The vendored babelfish must be importable as a top-level package."""
    import providers._vendor  # noqa: F401

    import babelfish

    assert hasattr(babelfish, "Language"), "babelfish.Language class missing"
    de = babelfish.Language("deu")
    assert de.alpha2 == "de"


def test_subliminal_can_use_babelfish():
    """Subliminal's internal babelfish usage must work with our vendored copy."""
    import providers._vendor  # noqa: F401

    from subliminal.video import Video
    from babelfish import Language

    v = Video.fromname("Frozen.2013.720p.BluRay.x264-DON.mkv")
    assert v.title.lower() == "frozen"
    # Basic smoke — don't assert specifics, just ensure no import-time crash
    assert Language("eng") is not None
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_subliminal_vendor.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/providers/_vendor/babelfish backend/providers/_vendor/LICENSE_babelfish backend/providers/_vendor/VENDOR_PATCHES.md backend/tests/test_subliminal_vendor.py
git commit -m "feat(plan-b1): vendor babelfish 0.6.1"
```

---

## Task 5: Scaffold SubliminalProviderAdapter skeleton

**Files:**
- Create: `backend/providers/subliminal_adapter.py`
- Create: `backend/tests/test_subliminal_adapter.py`

- [ ] **Step 1: Write the failing test for the adapter constructor**

```python
# backend/tests/test_subliminal_adapter.py
"""Unit tests for SubliminalProviderAdapter."""

import pytest

import providers._vendor  # noqa: F401 — trigger sys.path shim at test-collection time

from providers.base import SubtitleProvider


def test_adapter_is_a_sublarr_provider():
    """SubliminalProviderAdapter must be a subclass of Sublarr's SubtitleProvider."""
    from providers.subliminal_adapter import SubliminalProviderAdapter

    assert issubclass(SubliminalProviderAdapter, SubtitleProvider)


def test_adapter_constructor_accepts_provider_class():
    """Constructor takes a Subliminal Provider class + Sublarr config kwargs."""
    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="test",
        password="test",
    )
    assert adapter.name == "opensubtitles_subliminal"
    assert adapter._subliminal_provider_cls is OpenSubtitlesProvider
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: `FAIL` with `ModuleNotFoundError: No module named 'providers.subliminal_adapter'`

- [ ] **Step 3: Write the skeleton**

```python
# backend/providers/subliminal_adapter.py
"""Thin adapter that wraps a Subliminal Provider class as a Sublarr SubtitleProvider.

Usage:

    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="...",
        password="...",
    )
    results = adapter.search(query)
    content = adapter.download(results[0])

The adapter translates between Sublarr's `VideoQuery` / `SubtitleResult` dataclasses
and Subliminal's `Video` / `Subtitle` types.
"""

from __future__ import annotations

import logging

import providers._vendor  # noqa: F401 — side-effect import adds vendor to sys.path

from providers.base import SubtitleProvider, SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


class SubliminalProviderAdapter(SubtitleProvider):
    """Wraps a Subliminal Provider class and exposes Sublarr's provider interface."""

    # Instance-level overrides so each adapter instance can present a distinct name
    name: str = "subliminal_adapter"

    def __init__(
        self,
        subliminal_provider_cls: type,
        provider_name: str,
        **config,
    ):
        super().__init__(**config)
        self._subliminal_provider_cls = subliminal_provider_cls
        self.name = provider_name
        self._impl = None  # Instantiated in initialize()

    def initialize(self):
        """Instantiate the wrapped Subliminal provider and enter its context."""
        self._impl = self._subliminal_provider_cls(**self._subliminal_kwargs())
        self._impl.initialize()

    def terminate(self):
        """Cleanly tear down the wrapped Subliminal provider."""
        if self._impl is not None:
            try:
                self._impl.terminate()
            finally:
                self._impl = None

    def _subliminal_kwargs(self) -> dict:
        """Subclasses of Subliminal providers accept different kwargs.

        The adapter forwards ALL non-empty values from self.config as kwargs.
        Subliminal providers that don't need certain kwargs ignore them.
        """
        return {k: v for k, v in self.config.items() if v not in (None, "")}

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Not yet implemented — filled in by Task 8."""
        raise NotImplementedError("search() wired up in Task 8")

    def download(self, result: SubtitleResult) -> bytes:
        """Not yet implemented — filled in by Task 9."""
        raise NotImplementedError("download() wired up in Task 9")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/subliminal_adapter.py backend/tests/test_subliminal_adapter.py
git commit -m "feat(plan-b1): scaffold SubliminalProviderAdapter skeleton"
```

---

## Task 6: Implement VideoQuery → subliminal.Video converter

**Files:**
- Modify: `backend/providers/subliminal_adapter.py`
- Modify: `backend/tests/test_subliminal_adapter.py`

- [ ] **Step 1: Write failing test for the episode converter**

Append to `backend/tests/test_subliminal_adapter.py`:

```python
def test_convert_episode_query_to_subliminal_episode():
    """A Sublarr VideoQuery for an episode becomes a subliminal.video.Episode."""
    from providers.base import VideoQuery
    from providers.subliminal_adapter import _to_subliminal_video
    from subliminal.video import Episode

    q = VideoQuery(
        file_path="/media/Show/S01E05.mkv",
        series_title="My Show",
        season=1,
        episode=5,
        release_group="GROUP",
        source="BluRay",
        resolution="1080p",
        video_codec="x264",
        year=2020,
    )
    v = _to_subliminal_video(q)
    assert isinstance(v, Episode)
    assert v.series == "My Show"
    assert v.season == 1
    assert v.episode == 5
    assert v.release_group == "GROUP"
    assert v.source == "BluRay"
    assert v.resolution == "1080p"


def test_convert_movie_query_to_subliminal_movie():
    """A Sublarr VideoQuery for a movie becomes a subliminal.video.Movie."""
    from providers.base import VideoQuery
    from providers.subliminal_adapter import _to_subliminal_video
    from subliminal.video import Movie

    q = VideoQuery(
        file_path="/media/Frozen.2013.mkv",
        title="Frozen",
        year=2013,
        release_group="DON",
        source="BluRay",
        resolution="720p",
    )
    v = _to_subliminal_video(q)
    assert isinstance(v, Movie)
    assert v.title == "Frozen"
    assert v.year == 2013
    assert v.release_group == "DON"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py::test_convert_episode_query_to_subliminal_episode tests/test_subliminal_adapter.py::test_convert_movie_query_to_subliminal_movie -v`
Expected: `FAIL` with `ImportError: cannot import name '_to_subliminal_video'`

- [ ] **Step 3: Implement the converter**

Add to `backend/providers/subliminal_adapter.py` (module level, below imports):

```python
from subliminal.video import Episode, Movie, Video


def _to_subliminal_video(query: VideoQuery) -> Video:
    """Convert a Sublarr VideoQuery into a subliminal Video/Episode/Movie.

    Only fields that Subliminal scoring/matching actually reads are forwarded.
    Missing fields are left as Subliminal's defaults (usually None/empty).
    """
    if query.is_episode:
        return Episode(
            name=query.file_path or f"{query.series_title}.S{query.season:02d}E{query.episode:02d}.mkv",
            series=query.series_title,
            season=query.season,
            episode=query.episode,
            title=query.episode_title or None,
            year=query.year,
            release_group=query.release_group or None,
            source=query.source or None,
            resolution=query.resolution or None,
            video_codec=query.video_codec or None,
            imdb_id=query.imdb_id or None,
        )
    return Movie(
        name=query.file_path or f"{query.title}.{query.year}.mkv",
        title=query.title,
        year=query.year,
        release_group=query.release_group or None,
        source=query.source or None,
        resolution=query.resolution or None,
        video_codec=query.video_codec or None,
        imdb_id=query.imdb_id or None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/subliminal_adapter.py backend/tests/test_subliminal_adapter.py
git commit -m "feat(plan-b1): implement VideoQuery -> subliminal.Video converter"
```

---

## Task 7: Implement subliminal.Subtitle → SubtitleResult converter

**Files:**
- Modify: `backend/providers/subliminal_adapter.py`
- Modify: `backend/tests/test_subliminal_adapter.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_subliminal_adapter.py`:

```python
def test_convert_subliminal_subtitle_to_sublarr_result():
    """A subliminal Subtitle becomes a SubtitleResult with mapped fields."""
    from babelfish import Language
    from providers.subliminal_adapter import _to_sublarr_result

    class _FakeSubtitle:
        """Stand-in for a Subliminal Subtitle (duck-typed)."""

        provider_name = "opensubtitles"
        id = "12345"
        language = Language("eng")
        hearing_impaired = True
        foreign_only = False
        release_group = "GROUP"
        fps = 23.976
        page_link = "https://example.com/12345"

    sub = _FakeSubtitle()
    result = _to_sublarr_result(sub, registered_name="opensubtitles_subliminal")

    assert result.provider_name == "opensubtitles_subliminal"
    assert result.subtitle_id == "12345"
    assert result.language == "en"
    assert result.hearing_impaired is True
    assert result.release_info == "GROUP"
    assert result.fps == 23.976
    assert result.download_url == "https://example.com/12345"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py::test_convert_subliminal_subtitle_to_sublarr_result -v`
Expected: `FAIL` with `ImportError: cannot import name '_to_sublarr_result'`

- [ ] **Step 3: Implement the converter**

Add to `backend/providers/subliminal_adapter.py`:

```python
from providers.base import SubtitleFormat


def _to_sublarr_result(subliminal_subtitle, registered_name: str) -> SubtitleResult:
    """Convert a Subliminal Subtitle into a Sublarr SubtitleResult.

    `registered_name` is the name under which the adapter is registered with
    Sublarr's provider registry (e.g. "opensubtitles_subliminal") — not the
    Subliminal-internal provider_name attribute. We use our own name so that
    circuit-breaker + scoring + rate-limit state stays scoped to the adapter.
    """
    s = subliminal_subtitle
    language_code = getattr(s.language, "alpha2", "") or str(getattr(s.language, "alpha3", ""))
    return SubtitleResult(
        provider_name=registered_name,
        subtitle_id=str(getattr(s, "id", "")),
        language=language_code,
        format=SubtitleFormat.UNKNOWN,  # Subliminal determines format on download
        filename=getattr(s, "filename", "") or "",
        download_url=getattr(s, "page_link", "") or "",
        hearing_impaired=bool(getattr(s, "hearing_impaired", False)),
        forced=bool(getattr(s, "foreign_only", False)),
        fps=getattr(s, "fps", None),
        release_info=str(getattr(s, "release_group", "") or ""),
        provider_data={"subliminal_subtitle": s},  # keep reference for download()
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/subliminal_adapter.py backend/tests/test_subliminal_adapter.py
git commit -m "feat(plan-b1): implement subliminal.Subtitle -> SubtitleResult converter"
```

---

## Task 8: Implement adapter.search()

**Files:**
- Modify: `backend/providers/subliminal_adapter.py`
- Modify: `backend/tests/test_subliminal_adapter.py`

- [ ] **Step 1: Write failing test (mocked Subliminal provider)**

Append to `backend/tests/test_subliminal_adapter.py`:

```python
def test_adapter_search_delegates_to_subliminal_and_converts_results():
    """adapter.search() invokes the wrapped provider and converts each Subtitle."""
    from unittest.mock import MagicMock
    from babelfish import Language
    from providers.base import VideoQuery
    from providers.subliminal_adapter import SubliminalProviderAdapter

    class _FakeSubtitle:
        provider_name = "opensubtitles"
        id = "sub1"
        language = Language("eng")
        hearing_impaired = False
        foreign_only = False
        release_group = "GRP"
        fps = None
        page_link = "url"
        filename = "f.srt"

    fake_impl = MagicMock()
    fake_impl.list_subtitles.return_value = [_FakeSubtitle(), _FakeSubtitle()]

    FakeProviderCls = MagicMock(return_value=fake_impl)

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=FakeProviderCls,
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    query = VideoQuery(
        file_path="/media/Show/S01E01.mkv",
        series_title="Show",
        season=1,
        episode=1,
        languages=["en"],
    )
    results = adapter.search(query)

    assert len(results) == 2
    assert all(r.provider_name == "opensubtitles_subliminal" for r in results)
    assert fake_impl.list_subtitles.called
    # First positional arg must be a subliminal.video.Video
    from subliminal.video import Video as _Video

    video_arg = fake_impl.list_subtitles.call_args.args[0]
    assert isinstance(video_arg, _Video)
    # Second positional arg must be a set of Language objects
    langs_arg = fake_impl.list_subtitles.call_args.args[1]
    assert Language("eng") in langs_arg


def test_adapter_search_empty_languages_returns_empty_list():
    """If the query requests no languages we return [] without calling Subliminal."""
    from unittest.mock import MagicMock
    from providers.base import VideoQuery
    from providers.subliminal_adapter import SubliminalProviderAdapter

    fake_impl = MagicMock()
    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=MagicMock(return_value=fake_impl),
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    results = adapter.search(VideoQuery(file_path="/x.mkv", title="X", languages=[]))
    assert results == []
    fake_impl.list_subtitles.assert_not_called()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v -k "adapter_search"`
Expected: 2 tests FAIL with `NotImplementedError` (from Task 5 stub).

- [ ] **Step 3: Implement search()**

Replace the `search()` stub in `backend/providers/subliminal_adapter.py`:

```python
    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search the wrapped Subliminal provider for subtitles matching query."""
        from babelfish import Language

        if not query.languages:
            return []

        # Convert ISO 639-1 codes in query.languages into babelfish Language objects.
        try:
            lang_set = {Language.fromalpha2(code) for code in query.languages}
        except ValueError as e:
            logger.warning("Invalid language code in query for %s: %s", self.name, e)
            return []

        video = _to_subliminal_video(query)

        try:
            subliminal_subtitles = self._impl.list_subtitles(video, lang_set)
        except Exception as e:
            logger.warning("Subliminal provider %s failed search: %s", self.name, e)
            return []

        return [_to_sublarr_result(s, self.name) for s in subliminal_subtitles]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/subliminal_adapter.py backend/tests/test_subliminal_adapter.py
git commit -m "feat(plan-b1): implement adapter.search() with language + error handling"
```

---

## Task 9: Implement adapter.download()

**Files:**
- Modify: `backend/providers/subliminal_adapter.py`
- Modify: `backend/tests/test_subliminal_adapter.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_subliminal_adapter.py`:

```python
def test_adapter_download_invokes_subliminal_and_returns_bytes():
    """adapter.download() mutates the stored subtitle via Subliminal then returns bytes."""
    from unittest.mock import MagicMock
    from providers.base import SubtitleResult
    from providers.subliminal_adapter import SubliminalProviderAdapter

    class _FakeSubtitle:
        content = None  # Subliminal sets this during download_subtitle()

    fake_sub = _FakeSubtitle()

    def _side_effect(subtitle):
        subtitle.content = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"

    fake_impl = MagicMock()
    fake_impl.download_subtitle.side_effect = _side_effect

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=MagicMock(return_value=fake_impl),
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    result = SubtitleResult(
        provider_name="opensubtitles_subliminal",
        subtitle_id="1",
        language="en",
        provider_data={"subliminal_subtitle": fake_sub},
    )
    content = adapter.download(result)

    assert content == b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
    fake_impl.download_subtitle.assert_called_once_with(fake_sub)


def test_adapter_download_missing_stored_subtitle_raises():
    """If the stored Subliminal Subtitle reference is missing we raise clearly."""
    from providers.base import SubtitleResult
    from providers.subliminal_adapter import SubliminalProviderAdapter
    from unittest.mock import MagicMock

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=MagicMock(),
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    result = SubtitleResult(
        provider_name="opensubtitles_subliminal",
        subtitle_id="x",
        language="en",
        provider_data={},
    )
    with pytest.raises(ValueError, match="subliminal_subtitle"):
        adapter.download(result)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v -k "adapter_download"`
Expected: 2 tests FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement download()**

Replace the `download()` stub in `backend/providers/subliminal_adapter.py`:

```python
    def download(self, result: SubtitleResult) -> bytes:
        """Download subtitle content via the wrapped Subliminal provider."""
        subliminal_sub = result.provider_data.get("subliminal_subtitle")
        if subliminal_sub is None:
            raise ValueError(
                "SubtitleResult from SubliminalProviderAdapter missing "
                "provider_data['subliminal_subtitle'] — results must come "
                "from the same adapter instance that produced them."
            )
        self._impl.download_subtitle(subliminal_sub)
        return subliminal_sub.content or b""
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_adapter.py -v`
Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/providers/subliminal_adapter.py backend/tests/test_subliminal_adapter.py
git commit -m "feat(plan-b1): implement adapter.download() with missing-ref guard"
```

---

## Task 10: Wire OpenSubtitles pilot via adapter

**Files:**
- Create: `backend/providers/subliminal_opensubtitles.py`
- Modify: `backend/providers/registry.py`
- Create: `backend/tests/test_subliminal_opensubtitles_pilot.py`

- [ ] **Step 1: Write failing pilot registration test**

```python
# backend/tests/test_subliminal_opensubtitles_pilot.py
"""Pilot test for opensubtitles_subliminal registration."""

import providers._vendor  # noqa: F401


def test_pilot_provider_registered():
    """After import_builtin_providers runs, 'opensubtitles_subliminal' is registered."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers

    import_builtin_providers()
    assert "opensubtitles_subliminal" in _PROVIDER_CLASSES
    cls = _PROVIDER_CLASSES["opensubtitles_subliminal"]
    assert cls.name == "opensubtitles_subliminal"


def test_pilot_provider_instantiates_via_adapter():
    """Instantiating opensubtitles_subliminal gives a SubliminalProviderAdapter."""
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers
    from providers.subliminal_adapter import SubliminalProviderAdapter

    import_builtin_providers()
    cls = _PROVIDER_CLASSES["opensubtitles_subliminal"]
    instance = cls(username="u", password="p")
    assert isinstance(instance, SubliminalProviderAdapter)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_subliminal_opensubtitles_pilot.py -v`
Expected: 2 tests FAIL — `opensubtitles_subliminal` not in `_PROVIDER_CLASSES`.

- [ ] **Step 3: Create the pilot wrapper module**

```python
# backend/providers/subliminal_opensubtitles.py
"""Pilot wrapper that exposes Subliminal's OpenSubtitles XML-RPC provider.

Registered as 'opensubtitles_subliminal' — distinct from Sublarr's native
'opensubtitles_fetch' (REST API with key pools) to keep circuit-breaker and
rate-limit state per-flavor.
"""

from __future__ import annotations

import providers._vendor  # noqa: F401 — side-effect import

from providers.registry import register_provider
from providers.subliminal_adapter import SubliminalProviderAdapter


@register_provider
class OpenSubtitlesSubliminalProvider(SubliminalProviderAdapter):
    """Subliminal's OpenSubtitles provider, wrapped through SubliminalProviderAdapter."""

    name = "opensubtitles_subliminal"
    languages = {"en", "de", "es", "fr", "it", "nl", "pl", "pt", "ru", "ja", "zh"}

    # Declarative config fields for the dynamic UI form
    config_fields = [
        {
            "key": "username",
            "label": "Username",
            "type": "text",
            "required": True,
            "default": "",
        },
        {
            "key": "password",
            "label": "Password",
            "type": "password",
            "required": True,
            "default": "",
        },
    ]

    def __init__(self, **config):
        from subliminal.providers.opensubtitles import OpenSubtitlesProvider

        super().__init__(
            subliminal_provider_cls=OpenSubtitlesProvider,
            provider_name="opensubtitles_subliminal",
            **config,
        )
```

- [ ] **Step 4: Add to _BUILTIN_PROVIDERS**

Edit `backend/providers/registry.py` — add `"opensubtitles_subliminal"` at the end of the `_BUILTIN_PROVIDERS` tuple (after `"embedded"`):

```python
_BUILTIN_PROVIDERS: tuple[str, ...] = (
    "opensubtitles",
    "jimaku",
    ...existing names...,
    "embedded",
    "subliminal_opensubtitles",  # NEW — module name, Subliminal-flavored pilot
)
```

Note the entry is the module filename (`subliminal_opensubtitles`), not the provider name (`opensubtitles_subliminal`). The registry imports by module name; the module registers the class under its own `name` attribute via the `@register_provider` decorator.

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_opensubtitles_pilot.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/providers/subliminal_opensubtitles.py backend/providers/registry.py backend/tests/test_subliminal_opensubtitles_pilot.py
git commit -m "feat(plan-b1): register pilot provider opensubtitles_subliminal"
```

---

## Task 11: Integration smoke test — provider manager discovers + instantiates adapter

**Files:**
- Modify: `backend/tests/test_subliminal_opensubtitles_pilot.py`

- [ ] **Step 1: Write failing integration test**

Append to `backend/tests/test_subliminal_opensubtitles_pilot.py`:

```python
def test_provider_manager_lists_subliminal_provider():
    """ProviderManager's available-provider list must include the pilot."""
    from providers import get_provider_manager

    mgr = get_provider_manager()
    mgr.reload_from_config()  # no-op if already initialized; idempotent
    names = {cls.name for cls in mgr.available_provider_classes()}
    assert "opensubtitles_subliminal" in names, (
        f"Expected 'opensubtitles_subliminal' in available providers, got {sorted(names)}"
    )
```

If `ProviderManager` does not have a method named `available_provider_classes`, locate the equivalent (e.g. a property `available_providers` or the internal `_PROVIDER_CLASSES` dict) by running:

```bash
grep -n "def available" backend/providers/*.py backend/providers/manager_*.py
```

and adapt the test accordingly, replacing `available_provider_classes()` with the actual API. If no public list exists, use `_PROVIDER_CLASSES` directly:

```python
def test_provider_manager_lists_subliminal_provider():
    from providers.registry import _PROVIDER_CLASSES, import_builtin_providers
    import_builtin_providers()
    assert "opensubtitles_subliminal" in _PROVIDER_CLASSES
```

- [ ] **Step 2: Run test to verify pass**

Run: `cd backend && python -m pytest tests/test_subliminal_opensubtitles_pilot.py -v`
Expected: 3 tests PASS.

- [ ] **Step 3: Run the full backend suite to verify no regressions**

Run: `cd backend && python -m pytest --tb=short -q --ignore=tests/performance`
Expected: all tests pass (294+ existing tests green, plus the new ~10 tests added in B1).

- [ ] **Step 4: Run ruff + format check**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: both exit 0 (no lint errors, no formatting drift).

If ruff flags the vendored tree, add an `exclude` entry to `pyproject.toml` under `[tool.ruff]`:

```toml
[tool.ruff]
# ...existing config...
extend-exclude = ["backend/providers/_vendor"]
```

Commit this change together with the integration test.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_subliminal_opensubtitles_pilot.py pyproject.toml
git commit -m "feat(plan-b1): ProviderManager smoke-test + exclude _vendor/ from ruff"
```

---

## Task 12: Deploy B1 to Cardinal

**Files:**
- Modify: `backend/VERSION`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Confirm pre-deploy checks all green**

Run:

```bash
cd backend && ruff check . && ruff format --check .
cd backend && python -m pytest --tb=short -q --ignore=tests/performance
```

Both must exit 0. If anything fails, fix and re-run before proceeding.

- [ ] **Step 2: Invoke the deploy skill**

Tell the orchestrator: **"Invoke the `deploy` skill."**

The skill:
1. Analyses commits since `0.63.0-beta` (the Plan A ship)
2. Auto-bumps to `0.64.0-beta` (minor — Plan B1 introduces new `feat:` commits)
3. Drafts a `CHANGELOG.md` entry titled `## [0.64.0-beta] - 2026-04-19`
4. Shows the version + changelog draft
5. Waits for confirmation
6. Writes `backend/VERSION` + `CHANGELOG.md`, commits, pushes
7. Builds the multi-arch Docker image, pushes to GHCR
8. Pulls + restarts on Cardinal
9. Runs `/api/v1/health` check + prunes old images

Expected draft includes lines like:

```markdown
## [0.64.0-beta] - 2026-04-19

### Added
- **Plan B Phase 1 — Subliminal vendor foundation** — vendored Subliminal 2.2.0 and babelfish 0.6.1 into backend/providers/_vendor/; added SubliminalProviderAdapter that wraps any Subliminal Provider as a Sublarr SubtitleProvider; registered opensubtitles_subliminal as the pilot flavor. First step toward Bazarr-grade provider coverage.
```

- [ ] **Step 3: Verify the pilot provider on prod**

Run:

```bash
curl -s -H "X-API-Key: $SUBLARR_API_KEY" http://192.168.178.36:5765/api/v1/translation/backends | python -c "import sys,json; d=json.load(sys.stdin); print('ok')"
```

And for providers specifically:

```bash
curl -s -H "X-API-Key: $SUBLARR_API_KEY" http://192.168.178.36:5765/api/v1/providers/list | python -m json.tool | grep -c "opensubtitles_subliminal"
```

Expected: `1` (the pilot provider is listed).

If `SUBLARR_API_KEY` is not in the shell environment, pull it from `/mnt/user/appdata/sublarr/.env` on Cardinal, or ask the user to run the curl with the key from the Settings → API Keys page.

- [ ] **Step 4: Tail prod logs for 60s to confirm no errors**

```bash
ssh root@192.168.178.36 "docker logs sublarr --tail 200" | grep -iE "(error|traceback|exception)" | head -20
```

Expected: no new error lines attributable to Plan B1. Pre-existing warnings are acceptable if they were present in the 0.63.0-beta log.

- [ ] **Step 5: Mark phase B1 complete in the phase tracker**

Append to `CHANGELOG.md` under the `## [0.64.0-beta] - 2026-04-19` section:

```markdown
### Plan B Progress

- Phase B1 — Subliminal vendor foundation: **shipped**
```

Commit:

```bash
git add CHANGELOG.md
git commit -m "docs(plan-b1): mark phase B1 shipped in changelog tracker"
git push
```

---

## Phase B1 Acceptance Checklist

- [ ] `backend/providers/_vendor/__init__.py` with sys.path shim present
- [ ] `backend/providers/_vendor/subliminal/` populated from v2.2.0
- [ ] `backend/providers/_vendor/babelfish/` populated from v0.6.1
- [ ] `VENDOR_PATCHES.md` records both source commits
- [ ] `SubliminalProviderAdapter` implemented with search() + download()
- [ ] `opensubtitles_subliminal` registered via `@register_provider`
- [ ] 9+ adapter unit tests pass
- [ ] 3 vendor smoke tests pass
- [ ] 3 pilot-registration tests pass
- [ ] Full backend suite green (294+ tests, no regressions)
- [ ] Ruff clean
- [ ] 0.64.0-beta built + deployed to Cardinal
- [ ] `/api/v1/providers/list` exposes `opensubtitles_subliminal` in prod
- [ ] No new errors in prod logs within 60s of deploy

## Next Phase

**B2 — Full Subliminal provider adoption.** Bring the remaining ~19 Subliminal providers online through the same adapter. Per-provider rate-limits declared. Circuit-breaker integration per-instance. Provider count after B2: ≥ 35.
