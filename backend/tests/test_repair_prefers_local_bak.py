"""A pristine .bak is the original — use it, and skip the download entirely.

``apply_mods`` copies the sidecar to ``.bak`` *before* it edits it, so on installs
where that backup was never clobbered the .bak IS the untouched provider file.
And we can prove it: ``subtitle_hashes`` holds the SHA-256 of the pristine
download, so a .bak that hashes to it is the original beyond doubt.

That makes those repairs free — no provider round-trip, no quota, instant. On the
reference library 103 of 180 German backups are still pristine; installs that
never went through the backup-path migration may have far more.

A .bak that does NOT hash to the pristine value is worthless (it was made from an
already-damaged file) and must be ignored — silently trusting it would write the
damage straight back.
"""

import io
from unittest.mock import patch

import pysubs2
import pytest

from services.repair.runner import RepairCandidate, obtain_original, repair_one


def _srt(cues) -> bytes:
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    return buf.getvalue().encode("utf-8")


def _hash(raw: bytes) -> str:
    import hashlib

    t = raw.decode("utf-8").strip().replace("\r\n", "\n")
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


ORIGINAL = _srt([(1000, 3000, "darf ich dich um eine Sache bitten?")])


@pytest.fixture
def damaged_with_bak(tmp_path):
    """A damaged sidecar whose .bak still holds the pristine original."""
    import os

    from services.repair.legacy_transform import replay_legacy_pipeline
    from subtitle_filename import bak_path_for

    sidecar = tmp_path / "Show - S01E01.de.srt"
    sidecar.write_bytes(replay_legacy_pipeline(ORIGINAL, fmt="srt"))

    bak = bak_path_for(str(sidecar))
    os.makedirs(os.path.dirname(bak), exist_ok=True)
    with open(bak, "wb") as fh:
        fh.write(ORIGINAL)
    return sidecar, bak


@pytest.fixture
def candidate(damaged_with_bak):
    sidecar, _bak = damaged_with_bak
    return RepairCandidate(
        file_path=str(sidecar),
        language="de",
        fmt="srt",
        original_hash=_hash(ORIGINAL),
        provider="opensubtitles",
        subtitle_id="6827171",
    )


def test_a_pristine_bak_is_used_instead_of_downloading(app_ctx, candidate):
    original, source = obtain_original(candidate)

    assert source == "bak"
    assert original == ORIGINAL


def test_repair_from_a_pristine_bak_costs_no_quota(app_ctx, candidate, damaged_with_bak):
    sidecar, _bak = damaged_with_bak

    with (
        patch("services.repair.runner.fetch_original") as download,
        patch("services.repair.runner._record_repair"),
    ):
        outcome = repair_one(candidate)

    download.assert_not_called(), "a provable local original must not cost a download"
    assert outcome.status == "repaired"
    assert "darf ich dich um eine Sache bitten?" in sidecar.read_text(encoding="utf-8")


def test_a_damaged_bak_is_ignored(app_ctx, candidate, damaged_with_bak):
    """A .bak made from an already-damaged file must never be trusted."""
    from services.repair.legacy_transform import replay_legacy_pipeline

    sidecar, bak = damaged_with_bak
    with open(bak, "wb") as fh:
        fh.write(replay_legacy_pipeline(ORIGINAL, fmt="srt"))  # the damaged content

    with (
        patch("services.repair.runner.fetch_original", return_value=ORIGINAL) as download,
        patch("services.repair.runner._record_repair"),
    ):
        outcome = repair_one(candidate)

    download.assert_called_once(), "a bak that fails the hash proof must fall back to the provider"
    assert outcome.status == "repaired"
    assert "darf ich dich um eine Sache bitten?" in sidecar.read_text(encoding="utf-8")


def test_no_bak_falls_back_to_the_provider(app_ctx, tmp_path):
    from services.repair.legacy_transform import replay_legacy_pipeline

    sidecar = tmp_path / "Other - S01E01.de.srt"
    sidecar.write_bytes(replay_legacy_pipeline(ORIGINAL, fmt="srt"))
    cand = RepairCandidate(
        file_path=str(sidecar),
        language="de",
        fmt="srt",
        original_hash=_hash(ORIGINAL),
        provider="opensubtitles",
        subtitle_id="1",
    )

    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL) as download:
        original, source = obtain_original(cand)

    download.assert_called_once()
    assert source == "provider"
    assert original == ORIGINAL
