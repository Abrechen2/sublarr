import os

from services.subtitle_health import scan as scan_mod
from services.subtitle_health.models import IssueType

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "subtitle_health")


def test_scan_episode_sidecars_only(monkeypatch):
    # No embedded streams (avoid ffmpeg); two sidecars, one mislabeled +
    # the de one carries an escape leak.
    monkeypatch.setattr(scan_mod, "_list_embedded_targets", lambda *a, **k: [])
    english = open(os.path.join(FIX, "english.srt"), "rb").read()
    leaky = b"1\n00:00:01,000 --> 00:00:02,000\nText\\Nmehr\n"

    sidecars = [
        {"path": "/m/x.de.srt", "lang": "de", "raw": leaky},
        {"path": "/m/x.en.srt", "lang": "en", "raw": english},
    ]
    result = scan_mod.scan_episode(episode_id=1, video_path="/m/x.mkv", sidecars=sidecars)
    types = {i.type for i in result.issues}
    assert IssueType.ASS_ESCAPE_LEAK in types
    assert all(i.raw_hash for i in result.issues)
    assert result.to_dict()["healthy"] is False
