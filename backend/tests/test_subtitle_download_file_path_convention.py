"""subtitle_downloads.file_path must always be the VIDEO path.

Regression coverage for a prod bug found 2026-07-08: MT, manual-upload,
whisper, and combine rows stored their own generated subtitle path in
``file_path`` instead of the video path, unlike provider downloads
(backend/wanted_search/process.py). History's preview button reconstructs
"{base}.{lang}.{fmt}" from ``file_path`` assuming it's the video -- so those
four sources double-suffixed the reconstructed path and 404'd. This test
locks in the shared invariant directly rather than per-caller, so any future
source that forgets it fails loudly.
"""

from __future__ import annotations

from db.models.providers import SubtitleDownload
from db.wanted import get_wanted_item, upsert_wanted_item
from extensions import db


def _preview_path(file_path: str, language: str, fmt: str) -> str:
    """Mirror frontend/src/pages/History.tsx's onPreview reconstruction."""
    last_dot = file_path.rfind(".")
    base = file_path[:last_dot] if last_dot > 0 else file_path
    return f"{base}.{language}.{fmt}"


def test_mt_row_file_path_reconstructs_the_real_output_path(app_ctx, tmp_path):
    from services import mt_provisional

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(item_type="episode", file_path=str(mkv), target_language="de")
    item = get_wanted_item(item_id)
    output_path = str(tmp_path / "ep.de.ass")

    mt_provisional.finalize_translation(item_id, item, output_path, "de", "ass")

    row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
    assert _preview_path(row.file_path, "de", "ass") == output_path


def test_manual_upload_row_file_path_reconstructs_the_real_output_path(app_ctx, tmp_path):
    from services.subtitle_upload import save_manual_subtitle

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    media_root = str(tmp_path)

    out_path = save_manual_subtitle(
        video_path=str(mkv),
        content=b"1\n00:00:00,000 --> 00:00:01,000\nHi\n",
        ext="srt",
        language="de",
        modifier=None,
        overwrite=True,
        media_roots=[media_root],
    )

    row = db.session.query(SubtitleDownload).filter_by(source="manual").one()
    assert _preview_path(row.file_path, "de", "srt") == out_path


def test_combined_row_file_path_reconstructs_the_real_output_path(app_ctx, tmp_path, monkeypatch):
    from services import combine_service

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    (tmp_path / "ep.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
    (tmp_path / "ep.de.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHallo\n")

    result = combine_service.combine_for_video(
        video_path=str(mkv),
        languages=["en", "de"],
        fmt="srt",
        position=None,
        media_roots=[str(tmp_path)],
    )

    row = db.session.query(SubtitleDownload).filter_by(source="combined").one()
    assert row.file_path == str(mkv)
    assert result["combined_path"] == str(tmp_path / "ep.en-de.combined.srt")
