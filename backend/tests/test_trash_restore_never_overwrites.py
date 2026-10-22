"""Restoring a trash batch never overwrites a subtitle saved since.

Codex review of 1.17.0-rc.11: quarantine now moves a wrong-episode subtitle
into the trash, so its replacement lands at the same path. Restoring the
batch moved the wrong file over the replacement (``shutil.move`` replaces
silently) and then deleted the batch: the good subtitle was gone for good.
"""

import os

_OLD = "1\n00:00:01,000 --> 00:00:02,000\nAlt\n"
_NEW = "1\n00:00:01,000 --> 00:00:02,000\nNeu\n"


def test_an_occupied_destination_is_left_alone(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()
    with open(os.path.join(temp_dir, "Show - S01E01.mkv"), "wb") as fh:
        fh.write(b"v")
    sidecar = os.path.join(temp_dir, "Show - S01E01.de.srt")
    with open(sidecar, "w", encoding="utf-8") as fh:
        fh.write(_OLD)

    batch_id = client.delete("/api/v1/library/subtitles", json={"paths": [sidecar]}).get_json()[
        "batch_id"
    ]
    with open(sidecar, "w", encoding="utf-8") as fh:
        fh.write(_NEW)
    resp = client.post(f"/api/v1/library/trash/{batch_id}/restore")

    assert resp.get_json() == {"restored": 0, "failed": 1}
    assert open(sidecar, encoding="utf-8").read() == _NEW
    batches = client.get("/api/v1/library/trash").get_json()["batches"]
    assert batch_id in [b["batch_id"] for b in batches], "the old file stays restorable"
