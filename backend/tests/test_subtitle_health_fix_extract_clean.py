from unittest.mock import patch

from services.subtitle_health.fixers import extract_clean_sidecar


def test_writes_clean_sidecar(tmp_path, app_ctx):
    leaky = b"1\n00:00:01,000 --> 00:00:02,000\nA\\NB\n"
    video = tmp_path / "show.mkv"
    video.write_bytes(b"fake")
    with patch(
        "services.subtitle_health.fixers.extract_clean_sidecar.extract_track_raw",
        return_value=leaky,
    ):
        res = extract_clean_sidecar.apply(str(video), sub_index=0, codec="subrip", lang="ger")
    out = tmp_path / "show.de.srt"  # ger normalised to de
    assert res["changed"] is True
    assert out.exists()
    assert b"\\N" not in out.read_bytes()


def test_refuses_to_overwrite_foreign_sidecar(tmp_path, app_ctx):
    leaky = b"1\n00:00:01,000 --> 00:00:02,000\nA\\NB\n"
    video = tmp_path / "show.mkv"
    video.write_bytes(b"fake")
    existing = tmp_path / "show.de.srt"
    existing.write_bytes(b"user-edited content")
    with patch(
        "services.subtitle_health.fixers.extract_clean_sidecar.extract_track_raw",
        return_value=leaky,
    ):
        res = extract_clean_sidecar.apply(str(video), sub_index=0, codec="subrip", lang="ger")
    assert res["changed"] is False
    assert existing.read_bytes() == b"user-edited content"
