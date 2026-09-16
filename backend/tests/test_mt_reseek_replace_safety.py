"""Replacing a machine translation must never leave an episode worse off.

Two defects in ``services.mt_reseek._replace_original`` (found 2026-09-16 while
preparing to approve 30 pending originals on prod):

1. The MT was trashed BEFORE the real search ran. When that second search came
   up empty, the episode was left with no subtitle at all, and the approve
   route still cleared the pending marker and answered ``approved``.
2. Only the file at the ORIGINAL's path was trashed. Prod MTs are ``.srt``,
   29 of the 30 originals are ``.ass`` — the MT stayed next to the original.

The MT row in ``subtitle_downloads`` is keyed by the VIDEO path (see
``services.mt_provisional.record_mt_output``), so these tests record it that
way — unlike the older integration tests, which key it by the sidecar path.
"""

import json
from datetime import UTC, datetime

import pytest

from db.models.core import WantedItem
from extensions import db


def _make_item(mkv_path: str, lang: str = "en") -> int:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=mkv_path,
        title="Test",
        season_episode="S01E11",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language=lang,
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item.id


def _record_mt(mkv_path: str, lang: str, fmt: str) -> None:
    from db.providers import record_subtitle_download

    record_subtitle_download(
        "translation",
        f"mt:ep.{lang}.{fmt}",
        lang,
        fmt,
        mkv_path,
        0,
        source="machine_translation",
        record_stats=False,
    )


@pytest.fixture
def episode(app_ctx, tmp_path, monkeypatch):
    """A video with an ``.en.srt`` machine translation (+ quality sidecar),
    recorded exactly as prod records it."""
    from config import get_settings

    monkeypatch.setattr(get_settings(), "media_path", str(tmp_path))
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    mt = tmp_path / "ep.en.srt"
    mt.write_bytes(b"MT-CONTENT")
    quality = tmp_path / "ep.en.srt.quality.json"
    quality.write_text("{}")
    _record_mt(str(mkv), "en", "srt")
    item_id = _make_item(str(mkv))
    return {"id": item_id, "mkv": mkv, "mt": mt, "quality": quality, "dir": tmp_path}


def _preview(ep, fmt="ass"):
    return {
        "status": "found",
        "dry_run": True,
        "provider": "animetosho",
        "score": 252,
        "output_path": str(ep["dir"] / f"ep.en.{fmt}"),
        "format": fmt,
    }


def _fake_search_installs(ep, fmt="ass"):
    def fake(item_id, auto_translate=None, dry_run=False, bypass_existing_target_check=False):
        out = ep["dir"] / f"ep.en.{fmt}"
        out.write_bytes(b"REAL-ORIGINAL")
        return {"wanted_id": item_id, "status": "found", "output_path": str(out)}

    return fake


def _trashed(ep, name):
    return list((ep["dir"] / ".sublarr_trash").rglob(name))


# ── Defect 2: the MT in another format must go ──────────────────────────────


def test_ass_original_retires_srt_machine_translation(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    monkeypatch.setattr("wanted_search.process_wanted_item", _fake_search_installs(episode))

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode)) is True

    assert (episode["dir"] / "ep.en.ass").read_bytes() == b"REAL-ORIGINAL"
    assert not episode["mt"].exists(), "MT .srt must not stay next to the original"
    assert not episode["quality"].exists()
    trashed = _trashed(episode, "ep.en.srt")
    assert len(trashed) == 1 and trashed[0].read_bytes() == b"MT-CONTENT"


def test_same_format_original_keeps_mt_recoverable(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    monkeypatch.setattr(
        "wanted_search.process_wanted_item", _fake_search_installs(episode, fmt="srt")
    )

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode, "srt"))

    assert episode["mt"].read_bytes() == b"REAL-ORIGINAL"
    trashed = _trashed(episode, "ep.en.srt")
    assert len(trashed) == 1 and trashed[0].read_bytes() == b"MT-CONTENT"


def test_subtitles_not_produced_by_translation_are_untouched(episode, monkeypatch):
    """A foreign-language or differently-tagged sidecar is not the MT."""
    from services.mt_reseek import _replace_original

    other = episode["dir"] / "ep.eng.srt"
    other.write_bytes(b"EXTRACTED")
    german = episode["dir"] / "ep.de.srt"
    german.write_bytes(b"GERMAN")
    monkeypatch.setattr("wanted_search.process_wanted_item", _fake_search_installs(episode))

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode))

    assert other.read_bytes() == b"EXTRACTED"
    assert german.read_bytes() == b"GERMAN"


# ── Defect 1: a failed install must leave the MT in place ───────────────────


@pytest.mark.parametrize("status", ["not_found", "duplicate_skipped", "error"])
def test_failed_install_restores_machine_translation(episode, monkeypatch, status):
    from services.mt_reseek import _replace_original

    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda item_id, **kw: {"wanted_id": item_id, "status": status},
    )
    monkeypatch.setattr("services.mt_reseek._mark_reseek_miss", lambda item_id: None)

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode)) is False

    assert episode["mt"].read_bytes() == b"MT-CONTENT"
    assert episode["quality"].exists()
    assert _trashed(episode, "ep.en.srt") == []


def test_crashing_install_restores_machine_translation(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    def boom(item_id, **kw):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr("wanted_search.process_wanted_item", boom)
    monkeypatch.setattr("services.mt_reseek._mark_reseek_miss", lambda item_id: None)

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode)) is False

    assert episode["mt"].read_bytes() == b"MT-CONTENT"


# ── Review follow-ups: success is what landed on disk, not the status ───────


def test_original_saved_but_bookkeeping_failed_counts_as_installed(episode, monkeypatch):
    """process.py swallows an exception raised after save_subtitle (e.g. the
    download record) and reports not_found. The original IS on disk, so the
    MT must not come back next to it."""
    from services.mt_reseek import _replace_original

    def saved_then_swallowed(item_id, **kw):
        (episode["dir"] / "ep.en.ass").write_bytes(b"REAL-ORIGINAL")
        return {"wanted_id": item_id, "status": "not_found"}

    monkeypatch.setattr("wanted_search.process_wanted_item", saved_then_swallowed)

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode)) is True
    assert not episode["mt"].exists()


def test_duplicate_of_a_genuine_original_counts_as_installed(episode, monkeypatch):
    """A duplicate_skipped pointing at a real original (not the retired MT)
    means the episode already has what we wanted; the search deleted the row."""
    from services.mt_reseek import _replace_original

    original = episode["dir"] / "ep.en.ass"
    original.write_bytes(b"REAL-ORIGINAL")
    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda item_id, **kw: {
            "wanted_id": item_id,
            "status": "duplicate_skipped",
            "output_path": str(original),
        },
    )

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode)) is True
    assert not episode["mt"].exists()


def test_every_recorded_machine_translation_format_is_retired(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    second = episode["dir"] / "ep.en.ass"
    second.write_bytes(b"MT-ASS")
    _record_mt(str(episode["mkv"]), "en", "ass")

    def installs_srt(item_id, **kw):
        episode["mt"].write_bytes(b"REAL-ORIGINAL")
        return {"wanted_id": item_id, "status": "found", "output_path": str(episode["mt"])}

    monkeypatch.setattr("wanted_search.process_wanted_item", installs_srt)

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode, "srt"))
    assert not second.exists()
    assert episode["mt"].read_bytes() == b"REAL-ORIGINAL"


def test_restore_never_overwrites_an_occupied_path(tmp_path):
    from services.mt_sidecars import restore

    original = tmp_path / "ep.en.srt"
    original.write_bytes(b"SOMETHING-NEW")
    trashed = tmp_path / "trash-ep.en.srt"
    trashed.write_bytes(b"MT-CONTENT")

    restore([(str(original), str(trashed))])

    assert original.read_bytes() == b"SOMETHING-NEW"
    assert trashed.read_bytes() == b"MT-CONTENT"


def test_failed_approve_does_not_turn_a_wanted_item_provisional(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    misses = []
    monkeypatch.setattr("services.mt_reseek._mark_reseek_miss", lambda item_id: misses.append(1))
    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda item_id, **kw: {"wanted_id": item_id, "status": "not_found"},
    )

    item = {"id": episode["id"], "status": "wanted", **_item(episode)}
    assert _replace_original(item, _preview(episode)) is False
    assert misses == []


def test_failed_reseek_of_a_provisional_item_is_a_miss(episode, monkeypatch):
    from services.mt_reseek import _replace_original

    misses = []
    monkeypatch.setattr("services.mt_reseek._mark_reseek_miss", lambda item_id: misses.append(1))
    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda item_id, **kw: {"wanted_id": item_id, "status": "not_found"},
    )

    item = {"id": episode["id"], "status": "provisional", **_item(episode)}
    assert _replace_original(item, _preview(episode)) is False
    assert misses == [1]


# ── Route: approve only reports success when something was installed ────────


def test_approve_keeps_marker_and_reports_failure_when_nothing_installed(temp_db, monkeypatch):
    from app import create_app

    app = create_app(testing=True)
    with app.app_context():
        from db.wanted import get_wanted_item, set_mt_pending_original

        item_id = _make_item("/media/approve_fail.mkv")
        set_mt_pending_original(item_id, json.dumps({"output_path": "/media/x.en.ass"}))

    monkeypatch.setattr("services.mt_reseek._replace_original", lambda item, payload: False)

    with app.test_client() as client:
        resp = client.post(f"/api/v1/wanted/{item_id}/mt-pending/approve")

    assert resp.status_code == 409
    assert "error" in resp.get_json()
    with app.app_context():
        assert get_wanted_item(item_id)["mt_pending_original"] is not None


def _item(ep):
    return {"file_path": str(ep["mkv"]), "target_language": "en"}


def test_successful_replacement_forgets_the_retired_translation(episode, monkeypatch):
    """Otherwise a later genuine .en.srt at that path would still count as MT."""
    from db.providers import get_machine_translation_sidecars
    from services.mt_reseek import _replace_original

    monkeypatch.setattr("wanted_search.process_wanted_item", _fake_search_installs(episode))

    assert _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode))

    assert get_machine_translation_sidecars(str(episode["mkv"])) == []


def test_failed_replacement_keeps_the_translation_record(episode, monkeypatch):
    from db.providers import get_machine_translation_sidecars
    from services.mt_reseek import _replace_original

    monkeypatch.setattr(
        "wanted_search.process_wanted_item",
        lambda item_id, **kw: {"wanted_id": item_id, "status": "not_found"},
    )
    monkeypatch.setattr("services.mt_reseek._mark_reseek_miss", lambda item_id: None)

    assert not _replace_original({"id": episode["id"], **_item(episode)}, _preview(episode))

    assert get_machine_translation_sidecars(str(episode["mkv"])) == [("en", "srt")]
