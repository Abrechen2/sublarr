"""A sidecar restored from the subtitle trash counts as unknown origin.

Every other restore path (.bak swap, history rollback, MT trash restore)
records a ``restored`` origin since 1.15.0 so policy B never trusts a file
whose content it cannot vouch for; the trash-batch restore did not (parked
in the 1.15.0 review, fixed 2026-09-26).
"""

import os
import time
from datetime import UTC, datetime, timedelta

_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


def test_a_trash_batch_restore_records_a_restored_origin(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    video = os.path.join(temp_dir, "Show - S01E01.mkv")
    with open(video, "wb") as fh:
        fh.write(b"v")
    sidecar = os.path.join(temp_dir, "Show - S01E01.de.srt")
    with open(sidecar, "w", encoding="utf-8") as fh:
        fh.write(_SRT)
    stamp = time.time() - 60
    os.utime(sidecar, (stamp, stamp))

    with client.application.app_context():
        from db.models.providers import SidecarOrigin, SubtitleDownload
        from extensions import db
        from services.foreign_tracks.sidecars import real_sidecar_languages

        db.session.add(
            SubtitleDownload(
                provider_name="subdl",
                subtitle_id="x",
                language="de",
                format="srt",
                file_path=video,
                score=100,
                source="provider",
                downloaded_at=datetime.now(UTC) - timedelta(seconds=30),
            )
        )
        db.session.commit()
        assert real_sidecar_languages(video, {"de"}) == {"de"}

    batch_id = client.delete("/api/v1/library/subtitles", json={"paths": [sidecar]}).get_json()[
        "batch_id"
    ]
    resp = client.post(f"/api/v1/library/trash/{batch_id}/restore")
    assert resp.status_code == 200
    assert os.path.exists(sidecar)

    with client.application.app_context():
        origins = [
            o.origin for o in db.session.query(SidecarOrigin).filter_by(video_path=video).all()
        ]
        assert "restored" in origins
        assert real_sidecar_languages(video, {"de"}) == set()
