"""Tests for new fields (term_type, confidence, approved) on glossary CRUD routes."""

import pytest


def test_create_entry_with_term_type(client):
    """POST /glossary with term_type='character' stores it correctly."""
    resp = client.post(
        "/api/v1/glossary",
        json={
            "source_term": "Naruto",
            "target_term": "Naruto",
            "term_type": "character",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["source_term"] == "Naruto"
    assert data["term_type"] == "character"


def test_create_entry_defaults(client):
    """POST /glossary without term_type defaults to 'other', approved=1, confidence=None."""
    resp = client.post(
        "/api/v1/glossary",
        json={
            "source_term": "Konoha",
            "target_term": "Konoha",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["term_type"] == "other"
    assert data["approved"] == 1
    assert data["confidence"] is None


def test_update_entry_approved(client):
    """PUT /glossary/<id> with approved=0 and then approved=1 updates correctly."""
    # Create an entry first
    create_resp = client.post(
        "/api/v1/glossary",
        json={
            "source_term": "Hokage",
            "target_term": "Hokage",
        },
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.get_json()["id"]

    # Set approved=0
    update_resp = client.put(
        f"/api/v1/glossary/{entry_id}",
        json={"approved": 0},
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["approved"] == 0

    # Set approved=1
    update_resp2 = client.put(
        f"/api/v1/glossary/{entry_id}",
        json={"approved": 1},
    )
    assert update_resp2.status_code == 200
    assert update_resp2.get_json()["approved"] == 1


def test_create_entry_with_confidence(client):
    """POST /glossary with confidence stores it correctly."""
    resp = client.post(
        "/api/v1/glossary",
        json={
            "source_term": "Jutsu",
            "target_term": "Technik",
            "confidence": 0.85,
            "approved": 0,
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert abs(data["confidence"] - 0.85) < 1e-6
    assert data["approved"] == 0


def test_update_entry_term_type(client):
    """PUT /glossary/<id> with term_type updates it."""
    create_resp = client.post(
        "/api/v1/glossary",
        json={"source_term": "Hidden Leaf", "target_term": "Verstecktes Blatt"},
    )
    assert create_resp.status_code == 201
    entry_id = create_resp.get_json()["id"]

    update_resp = client.put(
        f"/api/v1/glossary/{entry_id}",
        json={"term_type": "place"},
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["term_type"] == "place"
