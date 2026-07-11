"""Find subtitles the pre-1.6.6 pipeline rewrote, and resolve how to re-fetch them.

``save_subtitle()`` records the hash of a download *as it writes it*, and only
then runs the processing pipeline. So a stored hash that disagrees with the file
on disk means the pipeline rewrote the file — that is what makes a candidate.

Note what this does **not** say: it does not mean the file was *damaged*. The
pipeline also normalises quotes and syncs timings, which moves the hash without
harming a single word. On the production library every tracked sidecar had been
touched, but a dry run over 25 of them found only 1 with content actually
missing. Whether a file is damaged is only knowable by fetching the original and
replaying the old pipeline over it — which is what the runner does. Files that
turn out to be intact are recorded as ``undamaged`` so they are never fetched
again.

Nor is the stored hash a proof of the original: it is the hash of the file *as it
was written back then*, and the normalisation chain that produced those bytes has
changed since — it matched 0 of 8 sampled downloads. The proof lives in
``restore``. The one place the hash still holds is a ``.bak``, which *is* the file
as written.

Resolving the provider record is the awkward part. ``subtitle_downloads.file_path``
holds the **video** path for 7289 of 7297 rows, not the sidecar's — so the two
tables cannot be joined on path. The sidecar is matched to its video by stripping
the language and extension:

    <dir>/<stem>.de.srt   ->   <dir>/<stem>.<video ext>
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from sqlalchemy import text as sql

from extensions import db

# <stem>.<lang>[.<modifier>].<ext> — the shape Sublarr writes sidecars in.
_SIDECAR_RE = re.compile(
    r"^(?P<stem>.+?)\.(?P<lang>[a-z]{2,3}(?:\.[a-z]+)*)\.(?P<ext>srt|ass|ssa)$", re.IGNORECASE
)


@dataclass(frozen=True)
class RepairCandidate:
    """A sidecar the pipeline rewrote, and the provider file it came from."""

    file_path: str
    language: str
    fmt: str
    original_hash: str
    provider: str
    subtitle_id: str


@dataclass(frozen=True)
class ScanReport:
    candidates: list[RepairCandidate]
    untouched: int
    missing_from_disk: int
    unresolvable: int
    already_repaired: int

    @property
    def repairable(self) -> int:
        return len(self.candidates)


def content_hash(path: str) -> str | None:
    """SHA-256 of the file, normalised exactly like ``dedup_engine`` does."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").strip().replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _download_index(language: str | None) -> dict[tuple[str, str], tuple[str, str]]:
    """(video stem, language) -> (provider, subtitle_id), newest download wins."""
    where = "WHERE subtitle_id IS NOT NULL AND subtitle_id <> ''"
    params: dict = {}
    if language:
        where += " AND language = :lang"
        params["lang"] = language

    rows = db.session.execute(
        sql(f"""
            SELECT DISTINCT ON (file_path, language)
                   file_path, language, provider_name, subtitle_id
            FROM subtitle_downloads
            {where}
            ORDER BY file_path, language, downloaded_at DESC
        """),
        params,
    ).fetchall()

    index: dict[tuple[str, str], tuple[str, str]] = {}
    for video_path, lang, provider, subtitle_id in rows:
        stem = os.path.splitext(video_path)[0]
        index[(stem, lang)] = (provider, subtitle_id)
    return index


def _repaired_paths() -> dict[str, str]:
    """file_path -> hash of the file as repair left it, so a repair is done once."""
    try:
        # 'undamaged' counts too: the pipeline moved the file's hash but never harmed
        # its text. Re-checking it would cost a download to learn the same thing again.
        rows = db.session.execute(
            sql(
                "SELECT file_path, repaired_hash FROM subtitle_repairs "
                "WHERE status IN ('repaired', 'undamaged')"
            )
        ).fetchall()
    except Exception:  # noqa: BLE001 — table may not exist yet on an old DB
        return {}
    return {p: h for p, h in rows}


def scan(language: str | None = None, limit: int | None = None) -> ScanReport:
    """Report which sidecars the old pipeline rewrote and can be re-fetched."""
    where = ""
    params: dict = {}
    if language:
        where = "WHERE language = :lang"
        params["lang"] = language

    rows = db.session.execute(
        sql(f"SELECT file_path, content_hash, language, format FROM subtitle_hashes {where}"),
        params,
    ).fetchall()

    index = _download_index(language)
    repaired = _repaired_paths()

    candidates: list[RepairCandidate] = []
    untouched = missing = unresolvable = already = 0

    for path, stored_hash, lang, fmt in rows:
        if not os.path.exists(path):
            missing += 1
            continue

        actual = content_hash(path)
        if actual is None:
            missing += 1
            continue

        if actual == stored_hash:
            untouched += 1
            continue

        # Repaired already? Then the current content is repair's own output, and
        # differing from the pristine hash is expected — not damage.
        if repaired.get(path) == actual:
            already += 1
            continue

        match = _SIDECAR_RE.match(os.path.basename(path))
        if not match:
            unresolvable += 1
            continue

        stem = os.path.join(os.path.dirname(path), match.group("stem"))
        hit = index.get((stem, lang))
        if hit is None:
            unresolvable += 1
            continue

        provider, subtitle_id = hit
        candidates.append(
            RepairCandidate(
                file_path=path,
                language=lang,
                fmt=(fmt or match.group("ext")).lower().lstrip("."),
                original_hash=stored_hash,
                provider=provider,
                subtitle_id=str(subtitle_id),
            )
        )
        if limit and len(candidates) >= limit:
            break

    return ScanReport(
        candidates=candidates,
        untouched=untouched,
        missing_from_disk=missing,
        unresolvable=unresolvable,
        already_repaired=already,
    )
