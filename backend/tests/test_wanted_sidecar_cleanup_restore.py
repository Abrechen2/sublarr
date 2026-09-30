"""A sidecar removed by "Wanted -> Cleanup sidecars" can be restored in the UI.

External test of 1.15.0 (2026-09-30), on a byte-identical copy of real files:
the cleanup moved the ``.en.srt`` into ``.sublarr/trash/<date>/`` — not hard
deleted, but ``GET /api/v1/trash`` reported ``sidecar_batches: 0``. The file
was still on disk and out of reach: the trash page only lists manifest
batches under ``.sublarr_trash/``, the ones every other sidecar delete makes.
"""

from __future__ import annotations

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


def _setup(client, tmp_path):
    response = client.put("/api/v1/config", json={"media_path": str(tmp_path)})
    assert response.status_code == 200, response.get_json()
    video = tmp_path / "Cowboy Bebop - S01E01.mkv"
    video.write_bytes(b"v")
    (tmp_path / "Cowboy Bebop - S01E01.de.srt").write_bytes(_SRT)
    (tmp_path / "Cowboy Bebop - S01E01.en.srt").write_bytes(_SRT)
    with client.application.app_context():
        from db.wanted import update_wanted_status, upsert_wanted_item

        row_id, _ = upsert_wanted_item(
            "episode", str(video), title="Cowboy Bebop", target_language="de"
        )
        update_wanted_status(row_id, "extracted")
    return tmp_path / "Cowboy Bebop - S01E01.en.srt"


def test_the_trashed_sidecar_shows_up_as_a_trash_batch(client, tmp_path):
    english = _setup(client, tmp_path)

    response = client.post("/api/v1/wanted/cleanup", json={})
    assert response.status_code == 200, response.get_json()
    assert not english.exists()
    batch_id = response.get_json()["batch_id"]

    batches = client.get("/api/v1/trash").get_json()["sidecar_batches"]
    mine = [b for b in batches if b["batch_id"] == batch_id]
    assert len(mine) == 1, batches
    assert mine[0]["file_count"] == 1


def test_it_can_be_restored_from_there(client, tmp_path):
    english = _setup(client, tmp_path)
    batch_id = client.post("/api/v1/wanted/cleanup", json={}).get_json()["batch_id"]

    response = client.post(f"/api/v1/library/trash/{batch_id}/restore")

    assert response.status_code == 200, response.get_json()
    assert english.read_bytes() == _SRT
