from unittest.mock import patch

from services.subtitle_health.fixers import remux_track


def test_refuses_unsupported_codec(tmp_path, app_ctx):
    video = tmp_path / "x.mkv"
    video.write_bytes(b"fake")
    res = remux_track.apply(str(video), sub_index=0, codec="hdmv_pgs_subtitle", lang="ger")
    assert res["changed"] is False
    assert "unsupported" in res["reason"].lower()


def test_track_id_mapped_via_mkvmerge_json(tmp_path, app_ctx):
    video = tmp_path / "x.mkv"
    video.write_bytes(b"fake")
    fake_json = {
        "tracks": [
            {"id": 0, "type": "video", "codec": "AVC/H.264"},
            {
                "id": 1,
                "type": "subtitles",
                "codec": "SubRip/SRT",
                "properties": {"language": "ger", "track_name": "Deutsch"},
            },
        ]
    }
    leaky = b"1\n00:00:01,000 --> 00:00:02,000\nA\\NB\n"
    with (
        patch(
            "services.subtitle_health.fixers.remux_track._mkvmerge_identify", return_value=fake_json
        ),
        patch("services.subtitle_health.fixers.remux_track.extract_track_raw", return_value=leaky),
        patch(
            "services.subtitle_health.fixers.remux_track._run_mkvmerge_replace", return_value=True
        ),
        patch(
            "services.subtitle_health.fixers.remux_track._make_backup", return_value="/trash/x.mkv"
        ),
        patch("services.subtitle_health.fixers.remux_track._validate_remux", return_value=None),
        patch("os.replace"),
    ):
        res = remux_track.apply(str(video), sub_index=0, codec="subrip", lang="ger")
    assert res["changed"] is True
    assert res["status"] == "resolved"
