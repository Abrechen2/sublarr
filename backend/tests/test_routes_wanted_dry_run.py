"""Tests for POST /api/v1/wanted/dry-run (pipeline preview batch route)."""

from db.wanted import get_wanted_item, upsert_wanted_item


def _make_wanted_item(client, tmp_path, name="ep.mkv"):
    mkv = tmp_path / name
    mkv.touch()
    with client.application.app_context():
        row_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
        )
    return row_id


class TestDryRunValidation:
    def test_missing_item_ids(self, client):
        resp = client.post("/api/v1/wanted/dry-run", json={})
        assert resp.status_code == 400

    def test_empty_item_ids(self, client):
        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": []})
        assert resp.status_code == 400

    def test_non_integer_item_ids(self, client):
        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": ["abc"]})
        assert resp.status_code == 400

    def test_too_many_items(self, client):
        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": list(range(1, 20))})
        assert resp.status_code == 400


class TestDryRunExecution:
    def test_unknown_item_reports_error(self, client):
        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": [999999]})
        assert resp.status_code == 200
        results = resp.get_json()["results"]
        assert len(results) == 1
        assert results[0]["wanted_id"] == 999999
        assert results[0]["status"] == "error"

    def test_preview_result_passthrough_and_order(self, client, tmp_path, monkeypatch):
        id_a = _make_wanted_item(client, tmp_path, "a.mkv")
        id_b = _make_wanted_item(client, tmp_path, "b.mkv")

        def fake_process(item_id, dry_run=False, **kwargs):
            assert dry_run is True
            return {
                "wanted_id": item_id,
                "status": "found",
                "dry_run": True,
                "provider": "test_provider",
                "score": 123,
                "format": "ass",
                "output_path": f"/media/{item_id}.de.ass",
            }

        import wanted_search

        monkeypatch.setattr(wanted_search, "process_wanted_item", fake_process)

        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": [id_b, id_a]})
        assert resp.status_code == 200
        results = resp.get_json()["results"]
        assert [r["wanted_id"] for r in results] == [id_b, id_a]
        assert all(r["status"] == "found" for r in results)
        assert results[0]["provider"] == "test_provider"

    def test_status_restored_after_preview(self, client, tmp_path, monkeypatch):
        item_id = _make_wanted_item(client, tmp_path)

        def fake_process(inner_id, dry_run=False, **kwargs):
            # The real pipeline bumps the row to "searching" before it knows
            # it is a preview — simulate that mutation.
            from db.wanted import update_wanted_status

            update_wanted_status(inner_id, "searching")
            return {"wanted_id": inner_id, "status": "not_found", "dry_run": True}

        import wanted_search

        monkeypatch.setattr(wanted_search, "process_wanted_item", fake_process)

        with client.application.app_context():
            before = get_wanted_item(item_id)["status"]

        resp = client.post("/api/v1/wanted/dry-run", json={"item_ids": [item_id]})
        assert resp.status_code == 200

        with client.application.app_context():
            after = get_wanted_item(item_id)["status"]
        assert after == before, "dry run must not leave the item stuck in 'searching'"
