"""Trash machine translations that were written in the wrong language.

Until 1.14.3 every Ollama request asked the model for the GLOBAL direction
("from English to German") whatever the job wanted. A job for any other target
therefore wrote text in the configured target language into a sidecar labelled
with another one — on the reference install German text in ``.en.srt``, 39 of
40 sampled. The prompt is fixed; this repairs what it already wrote.

A file is repaired only when all three hold, so a correct translation from any
backend is never touched:

1. ``subtitle_downloads`` records it as a machine translation;
2. its language tag is not the configured target language;
3. its CONTENT is detected as the configured target language (lingua, >= 0.90).

Repair = move the sidecar (and its ``.quality.json``) to the recoverable trash,
forget its machine-translation record, and put a ``provisional`` wanted item
for that language back to ``wanted``. A pending original found for the item is
kept, so it stays approvable. Episodes without a wanted item are picked up by
the next wanted scan, which sees the language missing again.

Usage (from the backend directory, or ``/app`` in the container)::

    python -m scripts.repair_wrong_direction_mt            # dry run, lists files
    python -m scripts.repair_wrong_direction_mt --apply
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger("repair_wrong_direction_mt")

MIN_CONFIDENCE = 0.90


@dataclass(frozen=True)
class Candidate:
    video: str
    language: str
    fmt: str
    path: str
    detected: str
    confidence: float


@dataclass
class Report:
    planned: list[Candidate] = field(default_factory=list)
    trashed: list[tuple[Candidate, str]] = field(default_factory=list)
    requeued: list[int] = field(default_factory=list)
    errors: list[tuple[Candidate, str]] = field(default_factory=list)


def find_candidates() -> list[Candidate]:
    """Machine translations whose content is the configured target language."""
    from config import get_settings
    from config_language_data import normalize_language_code
    from db.providers import list_machine_translations
    from services.subtitle_health.checkers.language_mislabel import detect_content_language
    from translator.output_paths import get_output_path_for_lang

    target = normalize_language_code(get_settings().target_language or "")
    candidates: list[Candidate] = []
    for video, language, fmt in list_machine_translations():
        if normalize_language_code(language) == target:
            continue
        path = get_output_path_for_lang(video, fmt, language)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as fh:
                detected, confidence = detect_content_language(fh.read())
        except OSError as exc:
            logger.warning("cannot read %s: %s", path, exc)
            continue
        if detected == target and confidence >= MIN_CONFIDENCE:
            candidates.append(Candidate(video, language, fmt, path, detected, confidence))
    return candidates


def repair(candidates: list[Candidate], apply: bool) -> Report:
    """Trash each candidate and requeue its episode; ``apply=False`` only plans."""
    report = Report(planned=list(candidates))
    if not apply or not candidates:
        return report

    from config import get_settings
    from db.providers import delete_machine_translation_records
    from db.repositories.wanted import WantedRepository
    from db.wanted import update_wanted_status
    from services.sidecar_trash import get_batch_dir, trash_sidecar

    media_path = getattr(get_settings(), "media_path", "") or ""
    batch_dir = get_batch_dir(media_path, f"wrong-direction-mt-{datetime.now(UTC):%Y%m%d%H%M%S}")
    wanted = WantedRepository()
    for candidate in candidates:
        trashed_path, err = trash_sidecar(candidate.path, media_path, batch_dir)
        if err:
            report.errors.append((candidate, err))
            continue
        report.trashed.append((candidate, trashed_path))
        delete_machine_translation_records(candidate.video, candidate.language, candidate.fmt)
        for item in wanted.get_wanted_items_by_path(candidate.video):
            if (
                item.get("target_language") == candidate.language
                and item.get("status") == "provisional"
            ):
                update_wanted_status(item["id"], "wanted")
                report.requeued.append(item["id"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Trash machine translations written in the wrong language."
    )
    parser.add_argument("--apply", action="store_true", help="trash files (default: dry run)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    from app import create_app

    app = create_app()
    with app.app_context():
        report = repair(find_candidates(), apply=args.apply)

    for c in report.planned:
        print(f"{c.language}.{c.fmt}  detected={c.detected} ({c.confidence:.2f})  {c.path}")
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(
        f"{mode}: {len(report.planned)} wrong-language machine translation(s); "
        f"trashed {len(report.trashed)}, requeued {len(report.requeued)}, "
        f"errors {len(report.errors)}"
    )
    for c, err in report.errors:
        print(f"ERROR {c.path}: {err}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
