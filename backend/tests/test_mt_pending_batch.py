"""Approve several pending originals at once (owner request 2026-09-16).

Each approval runs a real provider search, about 30 s on RC, so a batch of 30
cannot be a single request. The batch endpoint validates, answers 202 and
approves the items one after another in the background with exactly the
single-item path: an original that does not install leaves the machine
translation in place and keeps the pending marker.
"""

import itertools
import json
from datetime import UTC, datetime

import pytest

from db.models.core import WantedItem
from extensions import db


@pytest.fixture
def app_and_client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield app, client


@pytest.fixture(autouse=True)
def _reset_batch_state():
    from services import mt_pending_approval

    mt_pending_approval.reset_for_tests()
    yield
    mt_pending_approval.reset_for_tests()


_paths = itertools.count(1)


def _item(pending: bool = True) -> int:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    row = WantedItem(
        item_type="episode",
        file_path=f"/media/batch_{next(_paths)}.mkv",
        title="T",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language="en",
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
        mt_pending_original=json.dumps({"provider": "animetosho", "score": 250})
        if pending
        else None,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"item_ids": []},
        {"item_ids": "1"},
        {"item_ids": [1, "2"]},
        {"item_ids": list(range(501))},
    ],
)
def test_invalid_batches_are_rejected(app_and_client, body):
    _app, client = app_and_client

    resp = client.post("/api/v1/wanted/mt-pending/approve-batch", json=body)

    assert resp.status_code == 400


def test_batch_is_accepted_and_skips_items_without_a_pending_original(app_and_client, monkeypatch):
    app, client = app_and_client
    started = []
    monkeypatch.setattr(
        "services.mt_pending_approval.submit_background",
        lambda fn, *a, **kw: started.append((fn, a)),
    )
    with app.app_context():
        pending = _item()
        plain = _item(pending=False)

    resp = client.post(
        "/api/v1/wanted/mt-pending/approve-batch", json={"item_ids": [pending, plain, 999999]}
    )

    assert resp.status_code == 202
    data = resp.get_json()
    assert data["accepted"] == [pending]
    assert sorted(data["skipped"]) == sorted([plain, 999999])
    assert len(started) == 1


def test_a_second_batch_while_one_runs_is_refused(app_and_client, monkeypatch):
    app, client = app_and_client
    monkeypatch.setattr("services.mt_pending_approval.submit_background", lambda *a, **kw: None)
    with app.app_context():
        first, second = _item(), _item()

    assert (
        client.post(
            "/api/v1/wanted/mt-pending/approve-batch", json={"item_ids": [first]}
        ).status_code
        == 202
    )
    resp = client.post("/api/v1/wanted/mt-pending/approve-batch", json={"item_ids": [second]})

    assert resp.status_code == 409


def test_the_worker_approves_one_by_one_and_keeps_what_did_not_install(app_and_client, monkeypatch):
    from db.wanted import get_wanted_item
    from services import mt_pending_approval

    app, _client = app_and_client
    with app.app_context():
        installs, fails = _item(), _item()
    seen = []

    def fake_replace(item, payload):
        seen.append(item["id"])
        return item["id"] == installs

    monkeypatch.setattr("services.mt_reseek._replace_original", fake_replace)

    assert mt_pending_approval.claim_batch([installs, fails])
    mt_pending_approval.run_batch(app, [installs, fails])

    assert seen == [installs, fails]
    with app.app_context():
        assert get_wanted_item(installs)["mt_pending_original"] is None
        assert get_wanted_item(fails)["mt_pending_original"] is not None
    state = mt_pending_approval.batch_state()
    assert state == {"running": False, "total": 2, "done": 2, "installed": 1, "kept": 1}


def test_a_crashing_item_does_not_stop_the_batch(app_and_client, monkeypatch):
    from services import mt_pending_approval

    app, _client = app_and_client
    with app.app_context():
        crashes, installs = _item(), _item()

    def fake_replace(item, payload):
        if item["id"] == crashes:
            raise RuntimeError("provider exploded")
        return True

    monkeypatch.setattr("services.mt_reseek._replace_original", fake_replace)

    mt_pending_approval.claim_batch([crashes, installs])
    mt_pending_approval.run_batch(app, [crashes, installs])

    state = mt_pending_approval.batch_state()
    assert state["running"] is False and state["installed"] == 1 and state["kept"] == 1


def test_the_pending_list_reports_batch_progress(app_and_client):
    from services import mt_pending_approval

    _app, client = app_and_client
    mt_pending_approval.claim_batch([1, 2, 3])

    data = client.get("/api/v1/wanted/mt-pending").get_json()

    assert data["batch"] == {"running": True, "total": 3, "done": 0, "installed": 0, "kept": 0}
