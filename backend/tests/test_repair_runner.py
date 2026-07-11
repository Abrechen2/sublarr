"""Repair overwrites files on disk. Every gate that stops it doing so wrongly.

1. The re-fetched bytes must hash to the pristine hash recorded at download time.
   Otherwise the provider's file changed and we are not holding the original.
2. The file on disk must be reproducible by replaying the old buggy pipeline.
   Otherwise a human edited it.
3. Quota exhaustion must stop the run cleanly, not corrupt or half-write.
"""

import io
from unittest.mock import patch

import pysubs2
import pytest

from services.repair.runner import (
    QuotaExhaustedError,
    RepairCandidate,
    repair_one,
    run_repair,
)


def _srt(cues) -> bytes:
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    return buf.getvalue().encode("utf-8")


ORIGINAL = _srt(
    [
        (1000, 3000, "darf ich dich um eine Sache bitten?"),
        (4000, 6000, "Ich bin hier, um zu helfen."),
    ]
)


def _hash(raw: bytes) -> str:
    import hashlib

    t = raw.decode("utf-8").strip().replace("\r\n", "\n")
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


@pytest.fixture
def damaged_file(tmp_path):
    from services.repair.legacy_transform import replay_legacy_pipeline

    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(replay_legacy_pipeline(ORIGINAL, fmt="srt"))
    return path


@pytest.fixture
def candidate(damaged_file):
    return RepairCandidate(
        file_path=str(damaged_file),
        language="de",
        fmt="srt",
        original_hash=_hash(ORIGINAL),
        provider="opensubtitles",
        subtitle_id="6827171",
    )


def _text_of(path) -> str:
    return path.read_text(encoding="utf-8")


def test_repairs_and_brings_the_words_back(app_ctx, candidate, damaged_file):
    assert "um eine Sache" not in _text_of(damaged_file)  # sanity: it is damaged

    with (
        patch("services.repair.runner.fetch_original", return_value=ORIGINAL),
        patch("services.repair.runner._record_repair"),
    ):
        outcome = repair_one(candidate)

    assert outcome.status == "repaired"
    assert "darf ich dich um eine Sache bitten?" in _text_of(damaged_file)
    assert "  " not in _text_of(damaged_file)


def test_refuses_when_it_is_not_the_right_original(app_ctx, candidate, damaged_file):
    """If no replay reproduces the file on disk, we cannot prove what we would

    overwrite — the download is a different subtitle, or the file was edited.
    """
    before = damaged_file.read_bytes()
    other = _srt([(1000, 3000, "Ein ganz anderer Untertitel.")])

    with patch("services.repair.runner.fetch_original", return_value=other):
        outcome = repair_one(candidate)

    assert outcome.status == "unprovable"
    assert damaged_file.read_bytes() == before, "the file must not be touched"


def test_refuses_a_hand_edited_file(app_ctx, candidate, damaged_file):
    """A hand edit is not reproducible from the original — so it is not provable."""
    damaged_file.write_bytes(_srt([(1000, 3000, "Meine eigene Übersetzung.")]))
    before = damaged_file.read_bytes()

    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL):
        outcome = repair_one(candidate)

    assert outcome.status == "unprovable"
    assert damaged_file.read_bytes() == before, "a hand-edited file must never be overwritten"


def test_dry_run_writes_nothing(app_ctx, candidate, damaged_file):
    before = damaged_file.read_bytes()

    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL):
        outcome = repair_one(candidate, dry_run=True)

    assert outcome.status == "repaired"
    assert damaged_file.read_bytes() == before


def test_quota_exhaustion_stops_the_run_cleanly(app_ctx, candidate):
    """Stop at the wall, report it, leave the rest for the next run."""
    calls = {"n": 0}

    def _fetch(_c):
        calls["n"] += 1
        if calls["n"] > 1:
            raise QuotaExhaustedError("daily allowance spent")
        return ORIGINAL

    with (
        patch("services.repair.runner.fetch_original", side_effect=_fetch),
        patch("services.repair.runner._record_repair"),
    ):
        run = run_repair([candidate, candidate, candidate])

    assert run.quota_exhausted is True
    assert run.repaired == 1
    assert len(run.outcomes) == 1, "no work is attempted after the quota is gone"
