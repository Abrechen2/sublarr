# backend/tests/test_detect_op_ed_route.py
"""Route tests for POST /api/v1/tools/detect-opening-ending."""

import os

import pytest


@pytest.fixture
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as c:
        yield c


def test_no_op_ed_returns_empty_detected(client, tmp_path):
    """Valid subtitle file with no OP/ED cues returns detected=[]."""
    f = tmp_path / "plain.ass"
    # Simple ASS with Default-style events only — no OP/ED
    f.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello.\n",
        encoding="utf-8",
    )
    resp = client.post(
        "/api/v1/tools/detect-opening-ending",
        json={"file_path": str(f)},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "detected"
    assert data["detected"] == []


def test_ass_with_opening_style_returns_op_region(client, tmp_path):
    """Valid ASS file with Opening style events returns OP region."""
    f = tmp_path / "anime.ass"
    f.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
        "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
        "Style: Opening,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:05.00,0:00:10.00,Opening,,0,0,0,,OP line 1\n"
        "Dialogue: 0,0:00:10.00,0:00:15.00,Opening,,0,0,0,,OP line 2\n"
        "Dialogue: 0,0:00:15.00,0:00:20.00,Opening,,0,0,0,,OP line 3\n"
        "Dialogue: 0,0:10:00.00,0:10:02.00,Default,,0,0,0,,Normal dialogue.\n",
        encoding="utf-8",
    )
    resp = client.post(
        "/api/v1/tools/detect-opening-ending",
        json={"file_path": str(f)},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "detected"
    assert any(r["type"] == "OP" for r in data["detected"])


def test_path_outside_media_path_returns_403(client, tmp_path):
    """File outside media_path returns 403."""
    import tempfile

    outside = os.path.join(tempfile.gettempdir(), "..", "outside.ass")
    resp = client.post(
        "/api/v1/tools/detect-opening-ending",
        json={"file_path": outside},
    )
    assert resp.status_code == 403


def test_unsupported_format_returns_400(client, tmp_path):
    """VTT file returns 400 (unsupported format)."""
    f = tmp_path / "sub.vtt"
    f.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello.\n", encoding="utf-8")
    resp = client.post(
        "/api/v1/tools/detect-opening-ending",
        json={"file_path": str(f)},
    )
    assert resp.status_code == 400


def test_nonexistent_file_returns_404(client, tmp_path):
    """Non-existent file path returns 404."""
    resp = client.post(
        "/api/v1/tools/detect-opening-ending",
        json={"file_path": str(tmp_path / "nonexistent.ass")},
    )
    assert resp.status_code == 404
