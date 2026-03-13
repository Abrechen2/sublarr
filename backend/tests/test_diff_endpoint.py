"""Tests for POST /tools/diff endpoint."""
import pytest


@pytest.fixture
def client(tmp_path):
    import os
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
    resp = client.post("/api/v1/tools/diff", json={"original": "not valid ass content", "modified": MOD_ASS})
    assert resp.status_code == 400
    assert "error" in (resp.get_json() or {})
