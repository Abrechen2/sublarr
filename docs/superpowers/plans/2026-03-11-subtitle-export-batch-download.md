# Subtitle Export and Batch Download Implementation Plan

For agentic workers: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Add HTTP endpoints to download individual subtitle sidecar files and export all series
subtitles as a ZIP, with download buttons in the SeriesDetail UI.

**Architecture:** Two new routes in backend/routes/subtitles.py. _get_series_path() resolves
series path via sonarr_client + map_path(). _scan_series_subtitles() wraps
export_manager._scan_subtitle_files(). Frontend adds two URL builder functions and download
anchor tags - no TanStack hooks needed (direct browser navigation).

**Tech Stack:** Flask send_file, Python zipfile/io.BytesIO, React, TypeScript,
is_safe_path() + sonarr_client + export_manager

---

## Chunk 1: Backend Routes + Tests

### Task 1: Write failing tests

**Files:**
- Create: backend/tests/test_subtitle_export.py

- [ ] **Step 1: Create the test file**

```python
import os
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import pytest

ALLOWED_EXTS = [".ass", ".srt", ".vtt", ".ssa", ".sub"]


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings
    reload_settings()
    yield tmp_path
    reload_settings()


@pytest.fixture
def sub_client(temp_db, media_dir):
    from app import create_app
    season_dir = media_dir / "ShowName" / "Season 01"
    season_dir.mkdir(parents=True)
    sub_file = season_dir / "ShowName.S01E01.de.ass"
    sub_file.write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c, sub_file, media_dir


class TestSingleFileDownload:
    def test_download_valid_subtitle(self, sub_client):
        c, sub_file, _ = sub_client
        resp = c.get(f"/api/v1/subtitles/download?path={sub_file}")
        assert resp.status_code == 200
        assert b"Script Info" in resp.data
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_download_missing_path_param(self, sub_client):
        c, _, _ = sub_client
        assert c.get("/api/v1/subtitles/download").status_code == 400

    def test_download_path_traversal(self, sub_client):
        c, _, _ = sub_client
        assert c.get("/api/v1/subtitles/download?path=/etc/passwd").status_code == 403

    def test_download_bad_extension(self, sub_client):
        c, _, media_dir = sub_client
        py_file = media_dir / "script.py"
        py_file.write_text("import os")
        assert c.get(f"/api/v1/subtitles/download?path={py_file}").status_code == 403

    def test_download_missing_file(self, sub_client):
        c, _, media_dir = sub_client
        missing = media_dir / "nonexistent.de.srt"
        assert c.get(f"/api/v1/subtitles/download?path={missing}").status_code == 404

    @pytest.mark.parametrize("ext", ALLOWED_EXTS)
    def test_download_allowed_extensions(self, sub_client, ext):
        c, _, media_dir = sub_client
        f = media_dir / f"test{ext}"
        f.write_text("content")
        assert c.get(f"/api/v1/subtitles/download?path={f}").status_code == 200


class TestSeriesZipExport:
    def test_export_series_zip_basic(self, sub_client):
        c, _, media_dir = sub_client
        series_path = str(media_dir / "ShowName")
        with patch("routes.subtitles._get_series_path", return_value=series_path):
            resp = c.get("/api/v1/series/1/subtitles/export")
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        with zipfile.ZipFile(BytesIO(resp.data)) as zf:
            assert any("de.ass" in n for n in zf.namelist())

    def test_export_series_zip_lang_filter(self, sub_client):
        c, _, media_dir = sub_client
        (media_dir / "ShowName" / "Season 01" / "ShowName.S01E01.en.srt").write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
        )
        series_path = str(media_dir / "ShowName")
        with patch("routes.subtitles._get_series_path", return_value=series_path):
            resp = c.get("/api/v1/series/1/subtitles/export?lang=de")
        assert resp.status_code == 200
        with zipfile.ZipFile(BytesIO(resp.data)) as zf:
            names = zf.namelist()
            assert all("de" in n for n in names)
            assert not any("en" in n for n in names)

    def test_export_series_zip_not_found(self, sub_client):
        c, _, _ = sub_client
        with patch("routes.subtitles._get_series_path", return_value=None):
            assert c.get("/api/v1/series/999/subtitles/export").status_code == 404

    def test_export_series_zip_path_safety(self, sub_client):
        c, _, _ = sub_client
        with patch("routes.subtitles._get_series_path", return_value="/etc"):
            assert c.get("/api/v1/series/1/subtitles/export").status_code == 403

    def test_export_series_zip_size_limit(self, sub_client, monkeypatch):
        c, _, media_dir = sub_client
        series_path = str(media_dir / "ShowName")
        big_file = media_dir / "ShowName" / "Season 01" / "big.de.ass"
        big_file.write_bytes(b"X" * (51 * 1024 * 1024))

        def fake_scan(path, warnings):
            return [{"path": str(big_file), "language": "de", "format": "ass"}]

        monkeypatch.setattr("routes.subtitles._scan_series_subtitles", fake_scan)
        with patch("routes.subtitles._get_series_path", return_value=series_path):
            assert c.get("/api/v1/series/1/subtitles/export").status_code == 413
```

- [ ] **Step 2: Run -- confirm FAIL**

```
cd backend && python -m pytest tests/test_subtitle_export.py -v 2>&1 | head -40
```

Expected: All fail (routes not implemented yet).

---

### Task 2: Implement single-file download route

**Files:**
- Modify: backend/routes/subtitles.py

- [ ] **Step 1: Add missing imports** (os, get_settings, is_safe_path, map_path already present)

```python
import io
import zipfile
from flask import send_file
```

- [ ] **Step 2: Append constant and route at end of subtitles.py**

```python
_SUBTITLE_DOWNLOAD_EXTS = {".ass", ".srt", ".vtt", ".ssa", ".sub"}


@bp.route("/subtitles/download", methods=["GET"])
def download_subtitle():
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path parameter required"}), 400
    settings = get_settings()
    if not is_safe_path(settings.media_path, path):
        return jsonify({"error": "Access denied"}), 403
    ext = os.path.splitext(path)[1].lower()
    if ext not in _SUBTITLE_DOWNLOAD_EXTS:
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))
```

- [ ] **Step 3: Run TestSingleFileDownload -- confirm PASS**

```
cd backend && python -m pytest tests/test_subtitle_export.py::TestSingleFileDownload -v
```

- [ ] **Step 4: Commit**

```
git add backend/routes/subtitles.py backend/tests/test_subtitle_export.py
git commit -m "feat: subtitle single-file download endpoint"
```

---

### Task 3: Implement series ZIP export route

**Files:**
- Modify: backend/routes/subtitles.py

- [ ] **Step 1: Append helpers after _SUBTITLE_DOWNLOAD_EXTS**

```python
_ZIP_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB


def _get_series_path(series_id: int) -> str | None:
    from sonarr_client import get_sonarr_client
    try:
        client = get_sonarr_client()
        series = client.get_series_by_id(series_id)
        if not series:
            return None
        raw_path = series.get("path", "")
        return map_path(raw_path) if raw_path else None
    except Exception:
        return None


def _scan_series_subtitles(series_path: str, warnings: list) -> list[dict]:
    from export_manager import _scan_subtitle_files
    return _scan_subtitle_files(series_path, warnings)
```

- [ ] **Step 2: Append the export route**

```python
@bp.route("/series/<int:series_id>/subtitles/export", methods=["GET"])
def export_series_subtitles(series_id: int):
    settings = get_settings()
    lang_filter = request.args.get("lang", "").strip().lower()

    series_path = _get_series_path(series_id)
    if not series_path:
        return jsonify({"error": "Series not found"}), 404
    if not is_safe_path(settings.media_path, series_path):
        return jsonify({"error": "Access denied"}), 403

    warnings: list = []
    subtitle_files = _scan_series_subtitles(series_path, warnings)
    if lang_filter:
        subtitle_files = [
            s for s in subtitle_files
            if f".{lang_filter}." in os.path.basename(s["path"]).lower()
        ]

    buf = io.BytesIO()
    total_bytes = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in subtitle_files:
            sub_path = sub["path"]
            if not os.path.isfile(sub_path):
                continue
            total_bytes += os.path.getsize(sub_path)
            if total_bytes > _ZIP_SIZE_LIMIT:
                return jsonify({"error": "Export too large (50 MB limit)"}), 413
            rel_path = os.path.relpath(sub_path, series_path)
            zf.write(sub_path, rel_path)

    buf.seek(0)
    series_name = os.path.basename(series_path.rstrip("/\\")) or f"series-{series_id}"
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{series_name}-subtitles.zip",
    )
```

- [ ] **Step 3: Run full test suite -- confirm PASS**

```
cd backend && python -m pytest tests/test_subtitle_export.py -v
```

Expected: All ~14 tests PASS.

- [ ] **Step 4: Commit**

```
git add backend/routes/subtitles.py
git commit -m "feat: series subtitle ZIP export endpoint"
```

---

## Chunk 2: Frontend

### Task 4: Add URL helper functions

**Files:**
- Modify: frontend/src/api/client.ts

- [ ] **Step 1: Check end of file**

```
tail -20 frontend/src/api/client.ts
```

- [ ] **Step 2: Append at end of client.ts**

```typescript
/** Returns a URL that triggers a browser download of a single subtitle file. */
export function getSubtitleDownloadUrl(path: string): string {
  return `/api/v1/subtitles/download?path=${encodeURIComponent(path)}`;
}

/** Returns a URL that triggers a ZIP download of all subtitles for a series. */
export function getSeriesSubtitleExportUrl(
  seriesId: number,
  lang?: string,
): string {
  const params = lang ? `?lang=${encodeURIComponent(lang)}` : "";
  return `/api/v1/series/${seriesId}/subtitles/export${params}`;
}
```

- [ ] **Step 3: Verify TypeScript**

```
cd frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```
git add frontend/src/api/client.ts
git commit -m "feat: add subtitle download and series export URL helpers"
```

---

### Task 5: Add download buttons to SeriesDetail

**Files:**
- Modify: frontend/src/pages/SeriesDetail.tsx

- [ ] **Step 1: Inspect before editing**

```
grep -n "sidecar\|\.path\b\|series\.id\|button\|Button\|actions\|header" frontend/src/pages/SeriesDetail.tsx | head -40
```

Read surrounding JSX to understand exact insertion points.

- [ ] **Step 2: Extend existing @/api/client import** with getSubtitleDownloadUrl,
getSeriesSubtitleExportUrl

- [ ] **Step 3: Add download icon anchor next to each sidecar badge** (each has .path)

```tsx
<a
  href={getSubtitleDownloadUrl(sidecar.path)}
  download
  title={`Download ${sidecar.language} ${sidecar.format}`}
  className="ml-1 text-neutral-400 hover:text-teal-400 transition-colors"
  onClick={(e) => e.stopPropagation()}
>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-3.5 w-3.5 inline"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
      clipRule="evenodd"
    />
  </svg>
</a>
```

- [ ] **Step 4: Add Export ZIP anchor in series header** (after existing action buttons)

```tsx
<a
  href={getSeriesSubtitleExportUrl(series.id)}
  download
  className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded bg-neutral-700 hover:bg-neutral-600 text-neutral-200 transition-colors"
  title="Download all subtitles for this series as ZIP"
>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-4 w-4"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
      clipRule="evenodd"
    />
  </svg>
  Export ZIP
</a>
```

- [ ] **Step 5: Verify**

```
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: No errors.

- [ ] **Step 6: Commit**

```
git add frontend/src/pages/SeriesDetail.tsx
git commit -m "feat: add subtitle download and ZIP export buttons to SeriesDetail"
```

---

### Task 6: Full verification + PR

- [ ] **Step 1:** Run backend tests

```
cd backend && python -m pytest tests/test_subtitle_export.py -v
```

All PASS.

- [ ] **Step 2:** Run frontend checks

```
cd frontend && npm run test -- --run && npm run lint && npx tsc --noEmit
```

All PASS.

- [ ] **Step 3: Create feature branch and PR**

```
git checkout -b feat/subtitle-export-batch-download
git push -u origin feat/subtitle-export-batch-download
```

PR title: feat: subtitle export API + series ZIP batch download

PR body:
Summary:
- GET /api/v1/subtitles/download?path= -- single subtitle file download (path-safe, ext whitelist)
- GET /api/v1/series/{id}/subtitles/export[?lang=] -- ZIP of all series subs, 50 MB cap
- Download icon next to each sidecar badge in SeriesDetail
- Export ZIP button in series header

Security:
- is_safe_path() on both endpoints -- no path traversal possible
- Extension whitelist: .ass/.srt/.vtt/.ssa/.sub only
- 50 MB ZIP limit
- Inherits global API-Key auth

Test plan:
- [ ] Backend tests green (test_subtitle_export.py, ~14 tests)
- [ ] Frontend lint + tsc clean
- [ ] Manual: download button triggers browser file download
- [ ] Manual: Export ZIP has Season subfolder structure
- [ ] Manual: lang filter excludes non-target files
- [ ] Manual: path traversal attempt returns 403
