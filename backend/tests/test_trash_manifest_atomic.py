"""A trash manifest rewrite that fails leaves the previous one readable.

Codex review of 1.17.0-rc.11: the quarantine rewrites a batch's manifest after
each file. ``open(..., "w")`` truncated it first, so a write that failed
halfway (disk full) left an unreadable manifest, and the trash page hides
batches without one — with their files.
"""

import json
import os
from unittest.mock import patch

import pytest

from services.sidecar_trash import write_manifest


def test_a_failed_rewrite_keeps_the_previous_manifest(tmp_path):
    files = [{"original": "/m/a.de.ass", "trashed": str(tmp_path / "a.de.ass")}]
    write_manifest(str(tmp_path), "b1", files, series_name="Show", language="de")

    with (
        patch("utils.atomic_write.os.replace", side_effect=OSError(28, "No space left")),
        pytest.raises(OSError),
    ):
        write_manifest(str(tmp_path), "b1", [*files, {"original": "/m/b", "trashed": "/t/b"}])

    manifest = json.load(open(os.path.join(tmp_path, "manifest.json")))
    assert manifest["files"] == files
    assert [n for n in os.listdir(tmp_path) if n != "manifest.json"] == []
