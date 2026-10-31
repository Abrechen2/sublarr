"""Every sidecar Sublarr writes gets the download's processing, whatever its path.

Audit #61 A24: automatic extraction processed only the primary sidecar, and a
manual single-track extraction none at all. A25: the extraction passed the
Sonarr id only, so a standalone series' own processing settings were ignored.
"""

from unittest.mock import MagicMock, patch

from services import embedded_extractor
from services.embedded_extractor import ExtractResult

SETTINGS = MagicMock(
    embedded_extract_remove_from_container=False,
    enable_subtitle_repair=False,
    target_language="de",
)


def _extract(tmp_path, item):
    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    de, en = str(tmp_path / "Ep.de.ass"), str(tmp_path / "Ep.en.ass")
    result = ExtractResult(
        any_extracted=True,
        extracted=[
            {"language": "de", "format": "ass", "sub_index": 0, "output_path": de},
            {"language": "en", "format": "ass", "sub_index": 1, "output_path": en},
        ],
        primary_output_path=de,
        primary_format="ass",
        primary_language="de",
        sidecars_trashed=0,
    )
    SETTINGS.media_path = str(tmp_path)
    with (
        patch("config.get_settings", return_value=SETTINGS),
        patch("db.wanted.get_wanted_item", return_value={"id": 1, "target_language": "de", **item}),
        patch("db.wanted.update_existing_sub"),
        patch("db.wanted.update_wanted_status"),
        patch("ass_utils.get_media_streams", return_value={"streams": []}),
        patch(
            "services.embedded_extractor.resolve_profile_for_item",
            return_value={"target_languages": ["de", "en"]},
        ),
        patch("services.embedded_extractor.extract_and_cleanup", return_value=result),
        patch("services.embedded_extractor.emit_event"),
        patch("services.embedded_extractor.log_activity"),
        patch("services.standalone_library.wanted_item_path_refusal", return_value=None),
        patch("services.processing_pipeline._run_pipeline_for_path") as pipeline,
    ):
        embedded_extractor.extract_embedded_sub(1, str(video))
    return pipeline, de, en


def test_every_extracted_language_is_processed(tmp_path):
    pipeline, de, en = _extract(tmp_path, {"sonarr_series_id": 7})

    assert sorted(c.args[0] for c in pipeline.call_args_list) == sorted([de, en])
    assert {c.kwargs["series_id"] for c in pipeline.call_args_list} == {7}


def test_a_standalone_series_passes_its_owner_key(tmp_path):
    pipeline, _, _ = _extract(tmp_path, {"standalone_series_id": 12})

    assert {c.kwargs["series_id"] for c in pipeline.call_args_list} == {-12}


def test_the_lookup_from_a_sidecar_knows_standalone_series(tmp_path):
    from services.processing_pipeline import series_key_for_sidecar

    with patch(
        "db.wanted.get_wanted_items_by_path",
        side_effect=lambda p: [{"standalone_series_id": 12}] if p.endswith("Ep.mkv") else [],
    ):
        assert series_key_for_sidecar(str(tmp_path / "Ep.de.srt")) == -12


def test_a_manual_track_extraction_is_processed(client, tmp_path):
    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    stream = {
        "index": 2,
        "codec_type": "subtitle",
        "codec_name": "ass",
        "tags": {"language": "eng"},
    }
    with (
        patch("routes.tracks._get_video_path", return_value=str(video)),
        patch("routes.tracks.get_media_streams", return_value={"streams": [stream]}),
        patch("routes.tracks.extract_subtitle_stream") as extract,
        patch("services.processing_pipeline.process_new_sidecar") as process,
    ):
        response = client.post("/api/v1/library/episodes/5/tracks/2/extract", json={})

    assert response.status_code == 200, response.get_json()
    extract.assert_called_once()
    process.assert_called_once_with(response.get_json()["output_path"])
