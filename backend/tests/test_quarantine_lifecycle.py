"""Every job a quarantined sidecar meets in prod, run against one episode.

A sidecar quarantined as another episode's subtitle must keep its episode in
the wanted list, and its wrong bytes must never come to count as a subtitle
again, until a genuine replacement lands. Prod 1.17.0 lost that, one job at a
time, across three release candidates:

- rc.8: the "backups only" repair rewrote 14 quarantined files (the new bytes
  were no longer the flagged ones) and the wanted scan's cleanup dropped 16
  episodes, because the quarantined ASS was still on disk.
- rc.9: a search that found only an English source queued its translation;
  the translator saw the quarantined German ASS, answered "already exists",
  and the fallback deleted 23 wanted items as served.

Each test below is one of those jobs, run for real where it reads the disk or
the database; only ffprobe, providers, the LLM and ffsubsync are stubbed. The
invariant after every job is :func:`_still_waiting`.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from db.providers import record_subtitle_download
from db.wanted import get_wanted_items_by_path
from services import suspect_sidecars
from services.suspect_sidecars import is_suspect_sidecar, quarantine_wrong_sidecar

_ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
    "100,100,0,0,1,2,2,2,10,10,10,1\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{}\n"
)
#: As a provider serves them; save_subtitle normalises them before writing.
WRONG = _ASS.format("Text aus Staffel 1").encode()
GOOD = _ASS.format("Text aus Staffel 2").encode()
#: sidecar -> the wrong bytes as saved (normalised), recorded by the fixture.
_SAVED: dict[str, bytes] = {}


@pytest.fixture
def quarantined(app_ctx, tmp_path, monkeypatch):
    """An episode whose provider-downloaded German ASS was quarantined."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path), raising=False)
    season = tmp_path / "Show (2025)" / "Season 2"
    season.mkdir(parents=True)
    video = season / "Show - S02E06 - Whispers HDTV-1080p.mkv"
    video.write_bytes(b"\0" * 64)
    sidecar = season / "Show - S02E06 - Whispers HDTV-1080p.de.ass"
    # Saved the way prod saved it, so the flag's digest is of normalised bytes.
    _save(str(sidecar), WRONG, provider="animetosho", subtitle_id="at-123")
    _SAVED[str(sidecar)] = sidecar.read_bytes()
    suspect_sidecars.invalidate_cache()
    record_subtitle_download(
        "animetosho", "at-123", "de", "ass", str(video), 300, source="provider"
    )
    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("radarr_client.get_radarr_client", return_value=None),
    ):
        assert quarantine_wrong_sidecar(str(sidecar), str(video), "names S01E06, query is S02E06")
        assert _wanted(str(video)), "the quarantine requeues the episode"
        yield str(video), str(sidecar)
    suspect_sidecars.invalidate_cache()


def _wanted(video: str) -> list[dict]:
    return [i for i in get_wanted_items_by_path(video) if i.get("target_language") == "de"]


def _still_waiting(video: str, sidecar: str) -> None:
    suspect_sidecars.invalidate_cache()
    assert _wanted(video), "the episode left the wanted list with no replacement"
    if os.path.exists(sidecar):
        assert open(sidecar, "rb").read() == _SAVED[sidecar], "the quarantined file was rewritten"
        assert is_suspect_sidecar(sidecar), "the wrong bytes read as a genuine subtitle"


def _no_streams():
    return patch("translator.get_media_streams", return_value={"streams": []})


def _no_sources():
    """The translator finds no source subtitle anywhere, so it cannot finish."""
    return (
        patch("translator.core.find_any_source_sub", return_value=(None, None)),
        patch(
            "translator.core._search_providers_for_source_sub",
            return_value=(None, None, None, None),
        ),
    )


def _no_provider_hits(monkeypatch):
    manager = MagicMock()
    manager.search.return_value = []
    manager.search_and_download_best.return_value = None
    monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: manager)


# -- the scanners ---------------------------------------------------------------


def test_wanted_scan_cleanup(quarantined):
    from services.wanted_scanner_core import WantedScanner

    video, sidecar = quarantined
    scanner = WantedScanner.__new__(WantedScanner)
    with patch(
        "services.wanted_scanner_core.get_settings", return_value=MagicMock(upgrade_enabled=False)
    ):
        scanner._cleanup(set())

    _still_waiting(video, sidecar)


def test_wanted_scan_verdict(quarantined):
    from services.wanted_item_scanner import _check_language_for_item

    video, sidecar = quarantined
    verdict = _check_language_for_item(video, "de", None, MagicMock(upgrade_enabled=False))

    assert verdict is not None, "the scanner counts the episode as served"
    _still_waiting(video, sidecar)


def test_standalone_scan(quarantined):
    from standalone.scanner import StandaloneScanner

    video, sidecar = quarantined
    with patch("standalone.scanner._probe_embedded_tracks", return_value=None):
        assert StandaloneScanner()._check_existing_subtitle(video, "de") is None
    _still_waiting(video, sidecar)


# -- the search and the translations it hands on ----------------------------------


def test_search_without_hits_falls_back_to_translation(quarantined, monkeypatch):
    from wanted_search import process_wanted_item

    video, sidecar = quarantined
    _no_provider_hits(monkeypatch)
    sources, provider_sources = _no_sources()
    with _no_streams(), sources, provider_sources:
        process_wanted_item(_wanted(video)[0]["id"])

    _still_waiting(video, sidecar)


def test_queued_translation_of_a_downloaded_source(quarantined):
    """Prod rc.9: 23 episodes lost this way."""
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    video, sidecar = quarantined
    source = sidecar.replace(".de.ass", ".en.srt")
    with open(source, "w") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nText from season 2\n")
    sources, provider_sources = _no_sources()
    with _no_streams(), sources, provider_sources:
        try:
            SubtitleAutomationRunner()._translate_sidecar(_wanted(video)[0]["id"], video, "de")
        except RuntimeError:
            pass  # nothing to translate from in this test: a failure, booked for retry

    _still_waiting(video, sidecar)


# -- jobs that rewrite sidecars ---------------------------------------------------


def test_repair_from_backup(quarantined):
    """Prod rc.8: 14 quarantined files rewritten."""
    from services.repair.runner import RepairCandidate, repair_one

    video, sidecar = quarantined
    candidate = RepairCandidate(
        file_path=sidecar,
        language="de",
        fmt="ass",
        original_hash="irrelevant",
        provider="animetosho",
        subtitle_id="at-123",
    )
    # The pristine .bak holds the provider's file; replaying it repairs the text.
    with (
        patch("services.repair.runner.obtain_original", return_value=(WRONG, "backup")),
        patch("services.repair.runner.restore_subtitle", return_value=WRONG + b"\n"),
    ):
        repair_one(candidate)

    _still_waiting(video, sidecar)


def test_auto_sync(quarantined):
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    video, sidecar = quarantined

    def shift(path, _video):
        with open(path, "r+b") as fh:  # ffsubsync reads the file first
            fh.seek(0, os.SEEK_END)
            fh.write(b"\n")

    with patch("services.video_sync.sync_with_ffsubsync", side_effect=shift):
        try:
            SubtitleAutomationRunner()._auto_sync(sidecar, video)
        except FileNotFoundError:
            pass

    _still_waiting(video, sidecar)


def test_health_sweep_auto_fix(quarantined):
    from services.subtitle_health import sweep

    video, sidecar = quarantined
    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = video
    finding = {
        "id": 5,
        "suggested_fix": "repair_escapes",
        "target_kind": "sidecar",
        "target_path": sidecar,
    }

    def fix(_finding_id, _action):
        with open(sidecar, "ab") as fh:
            fh.write(b"\n")

    with (
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.sweep.scan_episode"),
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=True),
        patch("services.subtitle_health.sweep._is_stable", return_value=True),
        patch(
            "services.subtitle_health.sweep.store.get_findings_for_episode",
            return_value=[finding] if os.path.exists(sidecar) else [],
        ),
        patch("services.subtitle_health.sweep.apply_fix", side_effect=fix),
    ):
        sweep.subtitle_health_sweep_tick()

    _still_waiting(video, sidecar)


# -- downloads ------------------------------------------------------------------------


def _save(sidecar: str, content: bytes, *, provider: str, subtitle_id: str, matches=()):
    from providers.base import SubtitleFormat
    from tests.test_dedup_detection import _make_manager, _make_result

    result = _make_result(content)
    result.format = SubtitleFormat.ASS
    result.provider_name = provider
    result.subtitle_id = subtitle_id
    repo = MagicMock()
    repo.find_by_content_hash.return_value = list(matches)
    with patch("db.repositories.cleanup.CleanupRepository", return_value=repo):
        return _make_manager().save_subtitle(result, sidecar)


def test_the_same_bytes_from_another_provider(quarantined):
    """Neither saved again nor taken as a duplicate that serves the episode."""
    from error_handler import DuplicateSubtitleError

    video, sidecar = quarantined
    match = {"file_path": sidecar, "format": "ass", "language": "de"}
    with pytest.raises(RuntimeError) as rejected:
        _save(sidecar, WRONG, provider="subdl", subtitle_id="sd-9", matches=[match])

    assert not isinstance(rejected.value, DuplicateSubtitleError)
    _still_waiting(video, sidecar)


def test_a_genuine_replacement_ends_the_wait(quarantined):
    """The control: a different subtitle replaces the file and serves the episode."""
    from services.wanted_scanner_core import WantedScanner

    video, sidecar = quarantined
    _save(sidecar, GOOD, provider="subdl", subtitle_id="sd-10")

    suspect_sidecars.invalidate_cache()
    assert b"Staffel 2" in open(sidecar, "rb").read()
    assert not is_suspect_sidecar(sidecar)
    scanner = WantedScanner.__new__(WantedScanner)
    with patch(
        "services.wanted_scanner_core.get_settings", return_value=MagicMock(upgrade_enabled=False)
    ):
        scanner._cleanup(set())
    assert not _wanted(video)


# -- where the quarantined file goes (1.17.0-rc.11) ---------------------------------


def _trash_batches(media_root: str) -> list[dict]:
    import json

    from services.sidecar_trash import get_trash_root

    root = get_trash_root(media_root)
    if not os.path.isdir(root):
        return []
    return [
        json.load(open(os.path.join(root, entry, "manifest.json")))
        for entry in os.listdir(root)
        if os.path.isfile(os.path.join(root, entry, "manifest.json"))
    ]


def _media_root(sidecar: str) -> str:
    from config import get_settings

    return get_settings().media_path


def test_quarantine_moves_the_file_into_a_restorable_trash_batch(quarantined):
    video, sidecar = quarantined

    assert not os.path.exists(sidecar)
    [batch] = _trash_batches(_media_root(sidecar))
    [entry] = batch["files"]
    assert entry["original"] == sidecar
    assert open(entry["trashed"], "rb").read() == _SAVED[sidecar]
    _still_waiting(video, sidecar)


def test_a_file_the_trash_refuses_stays_flagged(app_ctx, tmp_path, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path), raising=False)
    video = tmp_path / "Show - S02E06.mkv"
    video.write_bytes(b"\0")
    sidecar = tmp_path / "Show - S02E06.de.ass"
    sidecar.write_bytes(WRONG)
    _SAVED[str(sidecar)] = WRONG
    suspect_sidecars.invalidate_cache()
    record_subtitle_download(
        "animetosho", "at-123", "de", "ass", str(video), 300, source="provider"
    )
    with (
        patch("sonarr_client.get_sonarr_client", return_value=None),
        patch("radarr_client.get_radarr_client", return_value=None),
        patch("services.sidecar_trash.trash_sidecar", return_value=(str(sidecar), "read-only")),
    ):
        assert quarantine_wrong_sidecar(str(sidecar), str(video), "names S01E06")

    assert sidecar.exists()
    _still_waiting(str(video), str(sidecar))


def test_files_flagged_while_kept_on_disk_go_to_the_trash(quarantined):
    """Prod: about 165 files were quarantined by rc.8-rc.10, which kept them."""
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [batch] = _trash_batches(_media_root(sidecar))
    os.replace(batch["files"][0]["trashed"], sidecar)  # as rc.10 left it
    suspect_sidecars.invalidate_cache()

    assert trash_quarantined_on_disk() == 1
    assert not os.path.exists(sidecar)
    assert trash_quarantined_on_disk() == 0
    _still_waiting(video, sidecar)


def test_a_file_the_user_restored_is_left_alone(quarantined):
    from services.subtitle_restore import mark_restored_safely
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [batch] = _trash_batches(_media_root(sidecar))
    os.replace(batch["files"][0]["trashed"], sidecar)
    mark_restored_safely(sidecar)
    suspect_sidecars.invalidate_cache()

    assert trash_quarantined_on_disk() == 0
    assert open(sidecar, "rb").read() == _SAVED[sidecar]


def test_the_full_wanted_scan_moves_them_out_first(quarantined):
    from services.wanted_scanner_core import WantedScanner

    video, sidecar = quarantined
    [batch] = _trash_batches(_media_root(sidecar))
    os.replace(batch["files"][0]["trashed"], sidecar)
    suspect_sidecars.invalidate_cache()

    scanner = WantedScanner()
    with (
        patch.object(scanner, "_scan_all_sonarr", return_value=(0, 0, {video})),
        patch.object(scanner, "_scan_all_radarr", return_value=(0, 0, set())),
        patch.object(scanner, "_scan_all_standalone", return_value=(0, 0, set())),
    ):
        scanner.scan_all(incremental=False)

    assert not os.path.exists(sidecar)
    _still_waiting(video, sidecar)


def test_the_same_bytes_under_another_language_code(quarantined):
    """Codex review of rc.11: ``.ger.ass`` is the same episode and language."""
    video, sidecar = quarantined
    alias = sidecar.replace(".de.ass", ".ger.ass")
    with pytest.raises(RuntimeError, match="quarantined"):
        _save(alias, WRONG, provider="subdl", subtitle_id="sd-9")

    assert not os.path.exists(alias)
    _still_waiting(video, sidecar)


def test_a_replacement_saved_while_the_sweep_runs_stays(quarantined):
    """Codex review of rc.11: the bytes are checked after the move, not before."""
    from services import sidecar_trash
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [batch] = _trash_batches(_media_root(sidecar))
    os.replace(batch["files"][0]["trashed"], sidecar)
    suspect_sidecars.invalidate_cache()
    real_trash = sidecar_trash.trash_sidecar

    def replaced_just_before(path, media_path, batch_dir):
        with open(path, "wb") as fh:  # the download lands between check and move
            fh.write(GOOD)
        return real_trash(path, media_path, batch_dir)

    with patch("services.sidecar_trash.trash_sidecar", side_effect=replaced_just_before):
        assert trash_quarantined_on_disk() == 0

    assert b"Staffel 2" in open(sidecar, "rb").read()


def test_a_file_whose_manifest_entry_fails_is_not_moved(quarantined):
    """Codex review of rc.11: a batch without its manifest cannot be restored."""
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [batch] = _trash_batches(_media_root(sidecar))
    os.replace(batch["files"][0]["trashed"], sidecar)
    suspect_sidecars.invalidate_cache()

    with patch("services.sidecar_trash.write_manifest", side_effect=OSError("disk full")):
        assert trash_quarantined_on_disk() == 0

    assert open(sidecar, "rb").read() == _SAVED[sidecar]
    _still_waiting(video, sidecar)


def test_a_moved_file_is_in_the_manifest_even_if_the_last_write_fails(quarantined):
    from services import sidecar_trash
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [old] = _trash_batches(_media_root(sidecar))
    os.replace(old["files"][0]["trashed"], sidecar)
    suspect_sidecars.invalidate_cache()
    real = sidecar_trash.write_manifest
    calls = []

    def first_only(*args, **kwargs):
        calls.append(args)
        if len(calls) > 1:
            raise OSError("disk full")
        return real(*args, **kwargs)

    with patch("services.sidecar_trash.write_manifest", side_effect=first_only):
        assert trash_quarantined_on_disk() == 1

    assert not os.path.exists(sidecar)
    batches = [b for b in _trash_batches(_media_root(sidecar)) if b["batch_id"] != old["batch_id"]]
    assert [f["original"] for b in batches for f in b["files"]] == [sidecar]
    assert all(os.path.exists(f["trashed"]) for b in batches for f in b["files"])


def test_a_replacement_that_cannot_go_back_stays_restorable(quarantined):
    """Replaced during the sweep, and replaced again before it could go back."""
    from services import sidecar_trash
    from services.suspect_sidecars import trash_quarantined_on_disk

    video, sidecar = quarantined
    [old] = _trash_batches(_media_root(sidecar))
    os.replace(old["files"][0]["trashed"], sidecar)
    suspect_sidecars.invalidate_cache()
    real_trash = sidecar_trash.trash_sidecar

    def replaced_twice(path, media_path, batch_dir):
        with open(path, "wb") as fh:
            fh.write(GOOD)
        out = real_trash(path, media_path, batch_dir)
        with open(path, "wb") as fh:
            fh.write(b"third")
        return out

    with patch("services.sidecar_trash.trash_sidecar", side_effect=replaced_twice):
        assert trash_quarantined_on_disk() == 0

    assert open(sidecar, "rb").read() == b"third"
    batches = [b for b in _trash_batches(_media_root(sidecar)) if b["batch_id"] != old["batch_id"]]
    [entry] = [f for b in batches for f in b["files"]]
    assert open(entry["trashed"], "rb").read() == GOOD


def test_an_embedded_ass_still_serves_while_something_is_suspect(quarantined, tmp_path):
    """Found by an order-dependent failure in the 1.17.0-rc.11 suite.

    Detection reads "ass" for an embedded target ASS. With any flag in the
    library (prod always has some), a genuine SRT sidecar beside it turned
    that into "srt", and the scanner wanted an episode the track serves.
    """
    from services.suspect_sidecars import existing_ignoring_suspects
    from services.wanted_item_scanner import _check_language_for_item

    other = tmp_path / "Other - S01E01.mkv"
    other.write_bytes(b"")
    (tmp_path / "Other - S01E01.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")
    probe = {
        "streams": [{"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "ger"}}]
    }

    assert existing_ignoring_suspects(str(other), "de", "ass") == "ass"
    assert (
        _check_language_for_item(str(other), "de", probe, MagicMock(upgrade_enabled=True)) is None
    )
