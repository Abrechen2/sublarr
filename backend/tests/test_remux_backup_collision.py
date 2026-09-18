"""Two videos of the same name must not share one backup in the trash.

Sandbox VM, 1.14.4-rc.7: ``_make_backup`` names the file after the basename and
whole seconds, so two different ``Show.mkv`` files backed up inside the same
second produced the same path — the second copy overwrote the first, and one
original had no backup left. Older than 1.14.4; the file is byte-identical to
rc.6.
"""

from __future__ import annotations

import os
import threading


def test_two_videos_of_the_same_name_keep_both_backups(tmp_path, app_ctx):
    from remux import _make_backup

    first_dir = tmp_path / "Season 1"
    second_dir = tmp_path / "Season 2"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "Show.mkv").write_bytes(b"AAAA")
    (second_dir / "Show.mkv").write_bytes(b"BBBB")

    first = _make_backup(str(first_dir / "Show.mkv"), False, str(tmp_path / ".sublarr"))
    second = _make_backup(str(second_dir / "Show.mkv"), False, str(tmp_path / ".sublarr"))

    assert first != second, "the second backup overwrote the first"
    assert os.path.exists(first) and os.path.exists(second)
    assert open(first, "rb").read() == b"AAAA"
    assert open(second, "rb").read() == b"BBBB"


def test_parallel_backups_of_the_same_name_do_not_collide(tmp_path, app_ctx):
    """The same pair, but both calls in flight at once.

    Sandbox VM, 1.14.4-rc.8: the rc.7 fix asked ``os.path.exists`` and only then
    copied, so two threads both saw a free path and copied onto it — 27 of 30
    synchronized pairs collided. ``routes/remux.py`` runs a real
    ``ThreadPoolExecutor(max_workers=2)``, and ``_jobs_lock`` guards the job
    status, not the backup. A barrier makes the overlap deterministic instead
    of hoping the scheduler interleaves the two calls.
    """
    from remux import _make_backup

    pairs = [("A", b"A" * 4096), ("B", b"B" * 4096)]
    for name, body in pairs:
        season = tmp_path / f"Season {name}"
        season.mkdir()
        (season / "Show.mkv").write_bytes(body)

    barrier = threading.Barrier(len(pairs))
    results: dict[str, str] = {}
    errors: list[BaseException] = []

    def run(name: str) -> None:
        try:
            barrier.wait(timeout=10)
            results[name] = _make_backup(
                str(tmp_path / f"Season {name}" / "Show.mkv"), False, str(tmp_path / ".sublarr")
            )
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(name,)) for name, _ in pairs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"backup raised: {errors}"
    assert len(set(results.values())) == len(pairs), f"both threads claimed one path: {results}"
    for name, body in pairs:
        assert open(results[name], "rb").read() == body, f"{name} lost its own bytes"
        assert (tmp_path / f"Season {name}" / "Show.mkv").read_bytes() == body
