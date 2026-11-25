"""Restoring one video purges only that video's sidecar trash (#48).

The purge matched batches by directory alone and removed whole batches, so
restoring Episode 01 also destroyed the trashed sidecars of every other
episode in the same season folder.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch


def _batch(trash_root, name, originals):
    batch = trash_root / name
    batch.mkdir(parents=True)
    files = []
    for original in originals:
        trashed = batch / os.path.basename(original)
        trashed.write_text("x")
        files.append({"original": original, "trashed": str(trashed)})
    (batch / "manifest.json").write_text(json.dumps({"batch_id": name, "files": files}))
    return batch


def _purge(tmp_path, video):
    from routes.remux import _purge_sidecars_for_video

    settings = MagicMock(media_path=str(tmp_path))
    with (
        patch("routes.remux.get_settings", return_value=settings),
        patch("routes.subtitles._get_trash_root", return_value=str(tmp_path / "trash")),
    ):
        return _purge_sidecars_for_video(video)


def test_only_the_restored_videos_sidecars_are_purged(client, tmp_path):
    season = str(tmp_path / "Show" / "Season 1")
    trash = tmp_path / "trash"
    own = _batch(trash, "a", [f"{season}/Ep01.de.srt"])
    mixed = _batch(trash, "b", [f"{season}/Ep01.en.srt", f"{season}/Ep02.de.srt"])
    other = _batch(trash, "c", [f"{season}/Ep02.en.srt"])

    _purge(tmp_path, f"{season}/Ep01.mkv")

    assert not own.exists()
    assert other.exists() and (other / "Ep02.en.srt").exists()
    assert (mixed / "Ep02.de.srt").exists()
    assert not (mixed / "Ep01.en.srt").exists()
    manifest = json.loads((mixed / "manifest.json").read_text())
    assert [f["original"] for f in manifest["files"]] == [f"{season}/Ep02.de.srt"]


def test_a_video_whose_name_prefixes_another_is_not_confused(client, tmp_path):
    season = str(tmp_path / "Show")
    trash = tmp_path / "trash"
    other = _batch(trash, "a", [f"{season}/Ep1.5.de.srt"])

    _purge(tmp_path, f"{season}/Ep1.mkv")

    # "Ep1.5.de.srt" belongs to "Ep1.5.mkv", not to "Ep1.mkv" — but only a
    # language suffix can tell them apart, so a non-language part keeps it.
    assert other.exists()
