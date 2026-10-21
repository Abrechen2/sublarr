"""Every free restore happens before any download, and a spent quota stops one provider only.

Prod 1.17.0-rc.6: 7,306 damaged sidecars, 3,401 with a pristine .bak (free) and
3,836 needing OpenSubtitles. The pass walked candidates in scan order and broke
off at the first QuotaExhaustedError, so backups behind that point waited a day
for the resume, other providers' repairs too — and the downloads competed with
the wanted search for the same OpenSubtitles allowance. A dry run downloaded
originals before discarding them.
"""

from unittest.mock import patch

import pytest

from services.repair.runner import QuotaExhaustedError, RepairCandidate, run_repair
from tests.test_repair_prefers_local_bak import ORIGINAL, _hash


def _sidecar(tmp_path, name, *, bak):
    import os

    from services.repair.legacy_transform import replay_legacy_pipeline
    from subtitle_filename import bak_path_for

    sidecar = tmp_path / f"{name}.de.srt"
    sidecar.write_bytes(replay_legacy_pipeline(ORIGINAL, fmt="srt"))
    if bak:
        path = bak_path_for(str(sidecar))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(ORIGINAL)
    return str(sidecar)


def _cand(path, provider):
    return RepairCandidate(
        file_path=path,
        language="de",
        fmt="srt",
        original_hash=_hash(ORIGINAL),
        provider=provider,
        subtitle_id=path,
    )


@pytest.fixture
def mixed(tmp_path):
    """Scan order puts OpenSubtitles first; backups and another provider behind it."""
    return [
        _cand(_sidecar(tmp_path, "A - S01E01", bak=False), "opensubtitles"),
        _cand(_sidecar(tmp_path, "B - S01E01", bak=True), "opensubtitles"),
        _cand(_sidecar(tmp_path, "C - S01E01", bak=False), "animetosho"),
        _cand(_sidecar(tmp_path, "D - S01E01", bak=False), "opensubtitles"),
        _cand(_sidecar(tmp_path, "E - S01E01", bak=True), "animetosho"),
    ]


def _fetch(calls):
    def fetch(candidate):
        calls.append(candidate.provider)
        if candidate.provider == "opensubtitles":
            raise QuotaExhaustedError("daily quota", reset_at=None)
        return ORIGINAL

    return fetch


def _statuses(run):
    return {o.file_path.rsplit("/", 1)[-1][:1]: o.status for o in run.outcomes}


def test_backups_are_restored_first_and_one_spent_quota_skips_only_its_provider(app_ctx, mixed):
    calls = []
    with (
        patch("services.repair.runner.fetch_original", side_effect=_fetch(calls)),
        patch("services.repair.runner._record_repair"),
    ):
        run = run_repair(mixed)

    assert _statuses(run) == {
        "B": "repaired",
        "E": "repaired",
        "A": "deferred",
        "C": "repaired",
        "D": "deferred",
    }
    assert calls == ["opensubtitles", "animetosho"], "the spent provider is asked once"
    assert run.quota_exhausted


def test_local_only_never_touches_a_provider(app_ctx, mixed):
    calls = []
    with (
        patch("services.repair.runner.fetch_original", side_effect=_fetch(calls)),
        patch("services.repair.runner._record_repair"),
    ):
        run = run_repair(mixed, local_only=True)

    assert calls == []
    assert _statuses(run) == {
        "B": "repaired",
        "E": "repaired",
        "A": "deferred",
        "C": "deferred",
        "D": "deferred",
    }


def test_a_backup_gone_since_the_scan_is_deferred_not_downloaded(app_ctx, mixed):
    import os

    from subtitle_filename import find_existing_bak

    calls = []
    with (
        patch("services.repair.runner.fetch_original", side_effect=_fetch(calls)),
        patch("services.repair.runner._record_repair"),
        patch(
            "services.repair.runner.order_local_first",
            side_effect=lambda cands: (
                [c for c in cands if find_existing_bak(c.file_path)],
                [c for c in cands if not find_existing_bak(c.file_path)],
            ),
        ) as order,
    ):
        local, _rest = order.side_effect(mixed)
        os.remove(find_existing_bak(local[0].file_path))
        run = run_repair(mixed, local_only=True)

    assert calls == []
    assert _statuses(run)["B"] == "deferred"


def test_a_dry_run_downloads_nothing(app_ctx, mixed):
    calls = []
    with patch("services.repair.runner.fetch_original", side_effect=_fetch(calls)):
        run = run_repair(mixed, dry_run=True)

    assert calls == []
    statuses = _statuses(run)
    assert statuses["B"] == "repaired" and statuses["A"] == "would_download"
