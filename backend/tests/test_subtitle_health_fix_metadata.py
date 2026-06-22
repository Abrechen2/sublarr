from unittest.mock import patch

from services.subtitle_health.fixers import metadata_correction


def test_sidecar_rename(tmp_path, app_ctx):
    p = tmp_path / "show.de.srt"
    p.write_bytes(b"actually english")
    res = metadata_correction.apply_sidecar_rename(str(p), new_lang="en")
    assert res["changed"] is True
    assert (tmp_path / "show.en.srt").exists()
    assert not p.exists()


def test_rename_rejects_bad_lang(tmp_path, app_ctx):
    p = tmp_path / "show.de.srt"
    p.write_bytes(b"x")
    res = metadata_correction.apply_sidecar_rename(str(p), new_lang="../evil")
    assert res["changed"] is False
    assert p.exists()  # not renamed


def test_embedded_uses_mkvpropedit(tmp_path, app_ctx):
    video = tmp_path / "show.mkv"
    video.write_bytes(b"fake")
    with patch(
        "services.subtitle_health.fixers.metadata_correction._run_mkvpropedit",
        return_value=True,
    ) as mp:
        res = metadata_correction.apply_embedded_lang(str(video), sub_index=1, new_lang="de")
    assert res["changed"] is True
    assert mp.called
