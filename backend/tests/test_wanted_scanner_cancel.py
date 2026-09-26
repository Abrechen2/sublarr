"""Review I-2: a cancelled or gate-refused probe must not become a wrong wanted row.

A probe the media IO gate refused (busy, or the run was stopped) came back as
None — the same value as "file has no streams" — and the scanner upserted the
episode with existing_sub="" / embedded_languages=[], overwriting a correct row.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.scheduler import cancellation


def _series_fixture(tmp_path):
    video = tmp_path / "ep01.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)
    sonarr = MagicMock()
    sonarr.get_episodes.return_value = [
        {
            "hasFile": True,
            "id": 10,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "episodeFile": {"path": mapped},
        }
    ]
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=True,
        upgrade_enabled=False,
        scan_metadata_max_workers=1,
    )
    return sonarr, settings, mapped


def _scan(sonarr, settings, mapped, *, probe_side_effect, upsert):
    from services.wanted_item_scanner import scan_sonarr_series

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch("services.wanted_item_scanner.get_settings", return_value=settings),
        patch(
            "services.wanted_item_scanner.get_series_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.get_media_streams", side_effect=probe_side_effect),
        patch("services.wanted_item_scanner.upsert_wanted_item", upsert),
    ):
        return scan_sonarr_series(sonarr, 1, settings, series_info={"title": "T"})


def test_batch_probe_marks_a_refused_probe_apart_from_a_failed_one():
    from services.media_io_gate import MediaGateBusyError
    from services.wanted_item_scanner import PROBE_REFUSED, batch_probe

    def _probe(path, _flag):
        if path == "/busy.mkv":
            raise MediaGateBusyError("busy")
        raise RuntimeError("broken file")

    with (
        patch(
            "services.wanted_item_scanner.get_settings",
            return_value=MagicMock(scan_metadata_max_workers=1),
        ),
        patch("services.wanted_item_scanner.get_media_streams", side_effect=_probe),
    ):
        results = batch_probe(["/busy.mkv", "/bad.mkv"])

    assert results["/busy.mkv"] is PROBE_REFUSED
    assert results["/bad.mkv"] is None


def test_gate_refused_episode_is_skipped_not_upserted(tmp_path):
    from services.media_io_gate import MediaGateBusyError

    sonarr, settings, mapped = _series_fixture(tmp_path)
    upsert = MagicMock(return_value=(1, True))

    added, updated, paths = _scan(
        sonarr, settings, mapped, probe_side_effect=MediaGateBusyError("busy"), upsert=upsert
    )

    upsert.assert_not_called()
    assert (added, updated) == (0, 0)
    # Still counted as seen, so a later prune does not treat it as deleted.
    assert mapped in paths


def test_cancel_during_the_probe_batch_upserts_nothing(tmp_path):
    sonarr, settings, mapped = _series_fixture(tmp_path)
    upsert = MagicMock(return_value=(1, True))
    event = cancellation.begin_run("wanted_scanner")
    token = cancellation.activate(event)

    def _probe_then_cancel(path, _flag):
        event.set()  # the user pressed stop while probes were running
        return {"streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {}}]}

    try:
        _added, _updated, paths = _scan(
            sonarr, settings, mapped, probe_side_effect=_probe_then_cancel, upsert=upsert
        )
    finally:
        cancellation.deactivate(token)
        cancellation.end_run("wanted_scanner", event)

    upsert.assert_not_called()
    assert mapped in paths
