"""A sidecar quarantined as another episode's subtitle is neither repaired nor forgotten.

Prod 1.17.0-rc.8 (2026-10-22): the wrong-episode audit quarantined 228 sidecars
and requeued their episodes. Two paths then undid that:

- The "backups only" repair restored 14 of them from their .bak. Rewriting the
  bytes moved the file's digest off the suspect flag, so the wrong subtitle read
  as genuine again (encoding fixed, still the wrong episode).
- Every wanted scan ends in a cleanup that drops items whose target ASS is on
  disk. It asked the disk without ``existing_ignoring_suspects``, so the 16
  quarantined ASS sidecars still waiting for a replacement lost their item.
"""

import os
from unittest.mock import MagicMock, patch

from db.wanted import get_wanted_items_by_path
from services import suspect_sidecars
from services.suspect_sidecars import is_suspect_sidecar, quarantine_wrong_sidecar
from tests.test_repair_encoding import ORIGINAL, _mangled, _scan_with
from tests.test_suspect_sidecars import _record, episode, no_arr  # noqa: F401 — fixtures


def _quarantine(video, sidecar):
    _record(video)
    assert quarantine_wrong_sidecar(sidecar, video, "names S01E06, query is S02E06")
    assert is_suspect_sidecar(sidecar)


def test_repair_leaves_a_quarantined_sidecar_alone(episode, no_arr):  # noqa: F811
    from services.repair.runner import RepairCandidate, repair_one

    video, sidecar = episode
    _quarantine(video, sidecar)
    before = open(sidecar, "rb").read()
    candidate = RepairCandidate(
        file_path=sidecar,
        language="de",
        fmt="ass",
        original_hash="irrelevant",
        provider="animetosho",
        subtitle_id="at-123",
    )

    with (
        patch("services.repair.runner._pristine_bak", return_value=b"bak") as bak,
        patch("services.repair.runner.fetch_original") as fetch,
    ):
        outcome = repair_one(candidate)

    assert outcome.status == "unavailable"
    assert "another episode" in outcome.detail
    bak.assert_not_called()
    fetch.assert_not_called()
    assert open(sidecar, "rb").read() == before
    assert is_suspect_sidecar(sidecar)


def test_scan_does_not_offer_a_quarantined_sidecar(app_ctx, tmp_path, no_arr):  # noqa: F811
    video = tmp_path / "Show - S01E01.mkv"
    video.touch()
    sidecar = tmp_path / "Show - S01E01.de.srt"
    sidecar.write_bytes(_mangled(ORIGINAL))
    suspect_sidecars.invalidate_cache()
    try:
        _record(str(video), fmt="srt")
        assert quarantine_wrong_sidecar(str(sidecar), str(video), "names S01E02")
        # _scan_with stubs db.session.execute; load the flags before it does.
        assert is_suspect_sidecar(str(sidecar))

        report = _scan_with(tmp_path, {"Show - S01E01.de.srt": (_mangled(ORIGINAL), "x")})
    finally:
        suspect_sidecars.invalidate_cache()

    assert report.candidates == []
    assert report.quarantined == 1


def test_wanted_cleanup_keeps_the_item_of_a_quarantined_ass(episode, no_arr):  # noqa: F811
    from services.wanted_scanner_core import WantedScanner

    video, sidecar = episode
    _quarantine(video, sidecar)
    assert get_wanted_items_by_path(video), "the quarantine requeues the episode"

    scanner = WantedScanner.__new__(WantedScanner)
    with patch(
        "services.wanted_scanner_core.get_settings", return_value=MagicMock(upgrade_enabled=False)
    ):
        removed = scanner._cleanup(set())

    assert removed == 0
    assert get_wanted_items_by_path(video)


def test_wanted_cleanup_still_drops_the_item_once_replaced(episode, no_arr):  # noqa: F811
    from services.wanted_scanner_core import WantedScanner

    video, sidecar = episode
    _quarantine(video, sidecar)
    with open(sidecar, "w") as fh:
        fh.write(open(sidecar).read() + "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,Neu\n")
    suspect_sidecars.invalidate_cache()

    scanner = WantedScanner.__new__(WantedScanner)
    with patch(
        "services.wanted_scanner_core.get_settings", return_value=MagicMock(upgrade_enabled=False)
    ):
        removed = scanner._cleanup(set())

    assert removed == 1
    assert not get_wanted_items_by_path(video)


def test_standalone_scan_does_not_count_a_quarantined_ass(episode, no_arr):  # noqa: F811
    from standalone.scanner import StandaloneScanner

    video, sidecar = episode
    _quarantine(video, sidecar)

    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        assert StandaloneScanner()._check_existing_subtitle(video, "de") is None


# -- other paths that would undo a quarantine (Codex review of rc.9) -----------


def test_fallback_translation_does_not_count_a_quarantined_sidecar(episode, no_arr):  # noqa: F811
    from wanted_search.process import _target_subtitle_on_disk

    video, sidecar = episode
    ctx = {"file_path": video, "item_lang": "de"}
    assert _target_subtitle_on_disk(ctx) == sidecar

    _quarantine(video, sidecar)

    assert _target_subtitle_on_disk(ctx) is None


def test_identical_bytes_from_another_provider_are_rejected_not_deduplicated(
    episode,  # noqa: F811
    no_arr,  # noqa: F811
):
    import pytest

    from tests.test_dedup_detection import _make_manager, _make_result

    video, sidecar = episode
    _quarantine(video, sidecar)
    from providers.base import SubtitleFormat

    result = _make_result(open(sidecar, "rb").read())
    result.format = SubtitleFormat.ASS
    repo = MagicMock()
    repo.find_by_content_hash.return_value = [
        {"file_path": sidecar, "format": "ass", "language": "de"}
    ]
    settings = MagicMock(media_path=os.path.dirname(sidecar), dedup_on_download=True)

    with (
        patch("config.get_settings", return_value=settings),
        patch("security_utils.is_safe_path", return_value=True),
        patch("db.repositories.cleanup.CleanupRepository", return_value=repo),
        patch("subtitle_normalise.normalise_downloaded_content", side_effect=lambda c, *a, **k: c),
        pytest.raises(RuntimeError, match="quarantined as another episode"),
    ):
        _make_manager().save_subtitle(result, sidecar)


def test_health_sweep_does_not_auto_fix_a_quarantined_sidecar(app_ctx):
    from services.subtitle_health import sweep

    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = "/m/e11.mkv"
    finding = {
        "id": 5,
        "suggested_fix": "repair_escapes",
        "target_kind": "sidecar",
        "target_path": "/m/e11.de.srt",
    }
    with (
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
        patch("services.subtitle_health.sweep.scan_episode"),
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=True),
        patch("services.subtitle_health.sweep._is_stable", return_value=True),
        patch(
            "services.subtitle_health.sweep.store.get_findings_for_episode", return_value=[finding]
        ),
        patch("services.subtitle_health.sweep.is_suspect_sidecar", return_value=True),
        patch("services.subtitle_health.sweep.apply_fix") as fix,
    ):
        sweep.subtitle_health_sweep_tick()

    fix.assert_not_called()


def test_translation_does_not_skip_over_a_quarantined_ass(episode, no_arr):  # noqa: F811
    """Prod rc.9 (2026-10-22): 23 quarantined episodes lost their wanted item.

    The search downloaded an English source and queued its translation; the
    translator found the quarantined German ASS, answered "already exists" and
    the fallback deleted the item as satisfied.
    """
    from translator import translate_file

    video, sidecar = episode
    with patch("translator.get_media_streams", return_value={"streams": []}):
        assert translate_file(video, target_language="de")["stats"].get("skipped")

        _quarantine(video, sidecar)
        with (
            patch("translator.core.find_any_source_sub", return_value=(None, None)) as source,
            patch("translator.core._search_providers_for_source_sub", return_value=(None, None, None, None)),
        ):
            result = translate_file(video, target_language="de")

    source.assert_called()
    assert "already exists" not in (result.get("stats") or {}).get("reason", "")
