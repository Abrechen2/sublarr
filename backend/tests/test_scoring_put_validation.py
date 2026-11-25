"""PUT /scoring/weights and /scoring/modifiers validate before writing (#56 sweep).

Weights had no range check at all, and an int beyond 64 bits failed with a 500
after earlier keys were saved. Modifiers were validated inside the write loop,
so an invalid value late in the payload left the earlier ones applied, and a
float infinity crashed int() with a 500.
"""

from __future__ import annotations

import pytest


def _weights(client):
    # Straight from the DB: the GET endpoint is response-cached.
    from db.scoring import get_all_scoring_weights

    with client.application.app_context():
        return get_all_scoring_weights()


def _modifiers(client):
    from db.scoring import get_all_provider_modifiers

    with client.application.app_context():
        return get_all_provider_modifiers()


def test_out_of_range_weight_is_refused_and_nothing_is_saved(client):
    before = _weights(client)
    rv = client.put("/api/v1/scoring/weights", json={"episode": {"series": 200, "hash": 10**30}})
    assert rv.status_code == 400
    assert _weights(client) == before


def test_unknown_weight_key_is_dropped_not_stored(client):
    rv = client.put("/api/v1/scoring/weights", json={"episode": {"nonsense": 5, "series": 201}})
    assert rv.status_code == 200
    weights = _weights(client)
    assert "nonsense" not in weights["episode"]
    assert weights["episode"]["series"] == 201


def test_valid_weights_are_saved(client):
    rv = client.put("/api/v1/scoring/weights", json={"episode": {"series": 200}})
    assert rv.status_code == 200
    assert _weights(client)["episode"]["series"] == 200


def test_bad_modifier_late_in_the_payload_saves_nothing(client):
    before = _modifiers(client)
    rv = client.put("/api/v1/scoring/modifiers", json={"opensubtitles": 10, "podnapisi": "oops"})
    assert rv.status_code == 400
    assert _modifiers(client) == before


def test_infinite_modifier_is_a_400_not_a_500(client):
    rv = client.put(
        "/api/v1/scoring/modifiers",
        data='{"opensubtitles": 1e400}',
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_a_section_that_is_not_an_object_is_refused(client):
    # Silently ignoring it answered 200 for a save that did nothing.
    rv = client.put("/api/v1/scoring/weights", json={"episode": [1, 2]})
    assert rv.status_code == 400


def _rule_weight(client, rule_id):
    rules = client.get("/api/v1/scoring/penalty-rules").get_json()["rules"]
    return next(r for r in rules if r["rule_id"] == rule_id)["current_weight"]


@pytest.mark.parametrize("bad", [2000, -1000, 1e400, 10**30])
def test_penalty_rule_weight_outside_the_range_is_refused(client, bad):
    # Same range as the weights; 1e400 used to crash int() with a 500 and the
    # UI spin box let 2000 through to be stored.
    before = _rule_weight(client, "release_group_match")
    rv = client.put("/api/v1/scoring/penalty-rules/release_group_match", json={"weight": bad})
    assert rv.status_code == 400
    assert _rule_weight(client, "release_group_match") == before


@pytest.mark.parametrize("edge", [-999, 999])
def test_penalty_rule_weight_at_the_range_edge_is_saved(client, edge):
    rv = client.put("/api/v1/scoring/penalty-rules/release_group_match", json={"weight": edge})
    assert rv.status_code == 200
    assert _rule_weight(client, "release_group_match") == edge
