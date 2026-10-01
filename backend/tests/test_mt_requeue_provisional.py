"""A machine-translated episode must stay with the re-seek, not drift back to wanted.

Owner policy (2026-09-13): a subtitle Sublarr translated itself is the last
resort and is replaced as soon as a genuine original exists. ``mt_reseek`` does
that, but only for ``provisional`` rows. Measured on prod 2026-10-01, three
defects kept the backlog away from it:

1. The scanners re-upsert every row they find and ``upsert_wanted_item``
   defaults to ``status="wanted"``. A machine-translated ``.srt`` reads as an
   upgrade candidate, so the next scan turned the provisional row back into a
   wanted one — 58 of the 63 rows carrying a found original were ``wanted``.
2. The ``mt_pending_original`` blob outlived that status change, so those 58
   rows advertised an original nothing would ever act on.
3. ``is_machine_translated`` answered True when *any* machine-translation row
   existed for the video, even when a genuine subtitle was downloaded later.
   With ``auto_replace`` on, that genuine subtitle would have been trashed.

See docs/superpowers/specs/2026-09-13-machine-translation-is-last-resort-design.md
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# 3. Provenance is the latest record for this video, language and format
# ---------------------------------------------------------------------------


def _record(path: str, lang: str, fmt: str, source: str) -> None:
    from db.providers import record_subtitle_download

    record_subtitle_download(
        provider_name="translation" if source == "machine_translation" else "opensubtitles",
        subtitle_id=f"{source}:{fmt}",
        language=lang,
        fmt=fmt,
        file_path=path,
        score=0,
        source=source,
        record_stats=False,
    )


def test_a_genuine_download_after_the_translation_wins(app_ctx):
    from db.providers import is_machine_translated

    _record("/media/a.mkv", "de", "ass", "machine_translation")
    _record("/media/a.mkv", "de", "ass", "provider")

    assert is_machine_translated("/media/a.mkv", "de", "ass") is False


def test_a_translation_after_a_genuine_download_is_ours(app_ctx):
    from db.providers import is_machine_translated

    _record("/media/b.mkv", "de", "srt", "provider")
    _record("/media/b.mkv", "de", "srt", "machine_translation")

    assert is_machine_translated("/media/b.mkv", "de", "srt") is True


def test_provenance_follows_the_format_that_is_on_disk(app_ctx):
    """Our ASS and a later genuine SRT can both sit next to the video."""
    from db.providers import is_machine_translated

    _record("/media/c.mkv", "de", "ass", "machine_translation")
    _record("/media/c.mkv", "de", "srt", "provider")

    assert is_machine_translated("/media/c.mkv", "de", "ass") is True
    assert is_machine_translated("/media/c.mkv", "de", "srt") is False


# ---------------------------------------------------------------------------
# 1a. The language check reports our own translation, ASS and SRT alike
# ---------------------------------------------------------------------------


def _check(existing: str, machine_translated: bool, *, upgrade_enabled: bool = True):
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=upgrade_enabled)
    with (
        patch(
            "services.wanted_item_scanner.detect_existing_target_for_lang", return_value=existing
        ),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
        patch("services.wanted_item_scanner.find_existing_target_file", return_value="/x.de.srt"),
        patch("services.wanted_item_scanner.score_existing_subtitle", return_value=("srt", 170)),
        patch(
            "services.wanted_item_scanner.is_machine_translated", return_value=machine_translated
        ),
    ):
        return _check_language_for_item("/media/ep.mkv", "de", None, settings, keep_seeking_mt=True)


def test_machine_translated_srt_is_flagged_and_not_an_upgrade():
    """Any genuine original beats our translation, so it carries no score to beat."""
    result = _check("srt", machine_translated=True)

    assert result["machine_translated"] is True
    assert result["upgrade_candidate"] is False
    assert result["current_score"] == 0


def test_machine_translated_srt_is_requeued_even_with_upgrades_off():
    result = _check("srt", machine_translated=True, upgrade_enabled=False)

    assert result is not None
    assert result["machine_translated"] is True


def test_machine_translated_ass_is_flagged():
    assert _check("ass", machine_translated=True)["machine_translated"] is True


def test_genuine_srt_stays_an_ordinary_upgrade_candidate():
    result = _check("srt", machine_translated=False)

    assert result["machine_translated"] is False
    assert result["upgrade_candidate"] is True


# ---------------------------------------------------------------------------
# 1b. Both Sonarr/Radarr scan paths requeue our translation as provisional
# ---------------------------------------------------------------------------

_KEEP_SEEKING_PROFILE = {
    "target_languages": ["de"],
    "target_language_names": ["German"],
    "forced_preference": "disabled",
    "mt_keep_seeking_original": 1,
}


def _scan_movie(tmp_path, *, machine_translated: bool, profile=None):
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)
    settings = MagicMock(use_embedded_subs=False, upgrade_enabled=True)
    upsert = MagicMock(return_value=(1, True))
    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value=profile or _KEEP_SEEKING_PROFILE,
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="srt"),
        patch("services.wanted_item_scanner.find_existing_target_file", return_value="/x.de.srt"),
        patch("services.wanted_item_scanner.score_existing_subtitle", return_value=("srt", 170)),
        patch(
            "services.wanted_item_scanner.is_machine_translated", return_value=machine_translated
        ),
        patch("services.wanted_item_scanner.upsert_wanted_item", upsert),
    ):
        scan_radarr_movie(
            MagicMock(), {"hasFile": True, "id": 7, "movieFile": {"path": mapped}}, settings
        )
    return upsert


def test_radarr_scan_requeues_our_translation_as_provisional(tmp_path):
    upsert = _scan_movie(tmp_path, machine_translated=True)

    assert upsert.call_args.kwargs["status"] == "provisional"


def test_radarr_scan_keeps_a_genuine_subtitle_wanted(tmp_path):
    upsert = _scan_movie(tmp_path, machine_translated=False)

    assert upsert.call_args.kwargs["status"] == "wanted"


def test_radarr_scan_without_keep_seeking_never_asks_for_provenance(tmp_path):
    profile = {**_KEEP_SEEKING_PROFILE, "mt_keep_seeking_original": 0}
    upsert = _scan_movie(tmp_path, machine_translated=True, profile=profile)

    assert upsert.call_args.kwargs["status"] == "wanted"


def test_sonarr_scan_requeues_our_translation_as_provisional(tmp_path):
    from services.wanted_item_scanner import scan_sonarr_series

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
    settings = MagicMock(use_embedded_subs=False, upgrade_enabled=True)
    upsert = MagicMock(return_value=(1, True))
    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_series_profile", return_value=_KEEP_SEEKING_PROFILE
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="ass"),
        patch("services.wanted_item_scanner.is_machine_translated", return_value=True),
        patch("services.wanted_item_scanner.upsert_wanted_item", upsert),
    ):
        scan_sonarr_series(sonarr, 1, settings, series_info={"title": "S"})

    assert upsert.call_args.kwargs["status"] == "provisional"


# ---------------------------------------------------------------------------
# 1c. The standalone scanner does the same
# ---------------------------------------------------------------------------


def test_standalone_requeues_our_translation_as_provisional():
    from standalone.scanner import StandaloneScanner

    scanner = StandaloneScanner.__new__(StandaloneScanner)
    with (
        patch("services.mt_provisional.resolve_keep_seeking", return_value=True),
        patch("db.providers.is_machine_translated", return_value=True),
    ):
        status = scanner._requeue_status("/media/ep.mkv", "de", "ass", {"standalone_series_id": 3})

    assert status == "provisional"


def test_standalone_keeps_a_genuine_subtitle_wanted():
    from standalone.scanner import StandaloneScanner

    scanner = StandaloneScanner.__new__(StandaloneScanner)
    with (
        patch("services.mt_provisional.resolve_keep_seeking", return_value=True),
        patch("db.providers.is_machine_translated", return_value=False),
    ):
        status = scanner._requeue_status("/media/ep.mkv", "de", "srt", {"standalone_series_id": 3})

    assert status == "wanted"


# ---------------------------------------------------------------------------
# 2. A found original is only advertised while the row is provisional
# ---------------------------------------------------------------------------


def test_leaving_provisional_drops_the_pending_original(app_ctx):
    from db.models.core import WantedItem
    from db.wanted import set_mt_pending_original, upsert_wanted_item
    from extensions import db

    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path="/media/pending.mkv",
        target_language="de",
        status="provisional",
    )
    set_mt_pending_original(row_id, '{"provider": "animetosho", "score": 291}')

    upsert_wanted_item(item_type="episode", file_path="/media/pending.mkv", target_language="de")

    row = db.session.get(WantedItem, row_id)
    assert row.status == "wanted"
    assert row.mt_pending_original is None


def test_staying_provisional_keeps_the_pending_original(app_ctx):
    from db.models.core import WantedItem
    from db.wanted import set_mt_pending_original, upsert_wanted_item
    from extensions import db

    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path="/media/pending2.mkv",
        target_language="de",
        status="provisional",
    )
    set_mt_pending_original(row_id, '{"provider": "animetosho", "score": 291}')

    upsert_wanted_item(
        item_type="episode",
        file_path="/media/pending2.mkv",
        target_language="de",
        status="provisional",
    )

    row = db.session.get(WantedItem, row_id)
    assert row.mt_pending_original is not None
