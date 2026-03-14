"""Tests for POST /tools/diff and POST /tools/diff/apply endpoints."""

import os

import pytest


@pytest.fixture
def client(tmp_path):
    os.environ["SUBLARR_MEDIA_PATH"] = str(tmp_path)
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as c, app.app_context():
        yield c
    del os.environ["SUBLARR_MEDIA_PATH"]
    reload_settings()


ORIG_ASS = """\
[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello world
Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,This is unchanged
"""

MOD_ASS = """\
[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hallo Welt
Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,This is unchanged
"""


# ── POST /tools/diff ────────────────────────────────────────────────────────────


def test_diff_returns_diffs(client):
    resp = client.post("/api/v1/tools/diff", json={"original": ORIG_ASS, "modified": MOD_ASS})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "diffs" in data
    assert data["changed"] >= 1


def test_diff_missing_original(client):
    resp = client.post("/api/v1/tools/diff", json={"modified": MOD_ASS})
    assert resp.status_code == 400


def test_diff_malformed_input(client):
    resp = client.post(
        "/api/v1/tools/diff", json={"original": "not valid ass content", "modified": MOD_ASS}
    )
    assert resp.status_code == 400
    assert "error" in (resp.get_json() or {})


def test_diff_identical_files_no_changes(client):
    resp = client.post("/api/v1/tools/diff", json={"original": ORIG_ASS, "modified": ORIG_ASS})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["changed"] == 0


def test_diff_missing_modified(client):
    resp = client.post("/api/v1/tools/diff", json={"original": ORIG_ASS})
    assert resp.status_code == 400


def test_diff_response_structure(client):
    resp = client.post("/api/v1/tools/diff", json={"original": ORIG_ASS, "modified": MOD_ASS})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "total" in data
    assert "changed" in data
    assert "diffs" in data
    assert isinstance(data["diffs"], list)
    # Check a modified entry has correct structure
    modified_entries = [d for d in data["diffs"] if d["type"] == "modified"]
    assert len(modified_entries) >= 1
    entry = modified_entries[0]
    assert "original" in entry
    assert "modified" in entry
    assert "start" in entry["original"]
    assert "end" in entry["original"]
    assert "text" in entry["original"]


# ── POST /tools/diff/apply ──────────────────────────────────────────────────────


def _write_sub_file(tmp_path, content, filename="test.de.ass"):
    """Write subtitle content to a file in tmp_path and return its path."""
    sub_file = tmp_path / filename
    sub_file.write_text(content, encoding="utf-8")
    return str(sub_file)


def test_apply_creates_backup(client, tmp_path):
    sub_file = _write_sub_file(tmp_path, MOD_ASS)
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": sub_file,
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "backup" in data
    assert os.path.exists(data["backup"])


def test_apply_returns_status_applied(client, tmp_path):
    sub_file = _write_sub_file(tmp_path, MOD_ASS)
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": sub_file,
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "applied"


def test_apply_accept_all_writes_modified_content(client, tmp_path):
    sub_file = _write_sub_file(tmp_path, MOD_ASS)
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": sub_file,
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 200
    written = open(sub_file, encoding="utf-8").read()
    assert "Hallo Welt" in written


def test_apply_reject_all_restores_original_content(client, tmp_path):
    sub_file = _write_sub_file(tmp_path, MOD_ASS)
    # Compute diff to get the index of the changed cue
    diff_resp = client.post("/api/v1/tools/diff", json={"original": ORIG_ASS, "modified": MOD_ASS})
    diffs = diff_resp.get_json()["diffs"]
    rejected = [i for i, d in enumerate(diffs) if d["type"] != "unchanged"]
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": sub_file,
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": rejected,
        },
    )
    assert resp.status_code == 200
    written = open(sub_file, encoding="utf-8").read()
    assert "Hello world" in written


def test_apply_missing_file_path(client):
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 400


def test_apply_path_traversal_rejected(client, tmp_path):
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": "/etc/passwd",
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 403


def test_apply_nonexistent_file(client, tmp_path):
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": str(tmp_path / "nonexistent.ass"),
            "original": ORIG_ASS,
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 404


def test_apply_malformed_original(client, tmp_path):
    sub_file = _write_sub_file(tmp_path, MOD_ASS)
    resp = client.post(
        "/api/v1/tools/diff/apply",
        json={
            "file_path": sub_file,
            "original": "not valid",
            "modified": MOD_ASS,
            "rejected_indices": [],
        },
    )
    assert resp.status_code == 400
