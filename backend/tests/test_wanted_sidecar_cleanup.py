"""Regression: "Wanted -> Cleanup sidecars" must never delete a wanted language.

VM test of 1.14.4-rc.2 (2026-09-17), reproduced against the route:

* Two ``extracted`` wanted items for the same episode, targets de and en, with
  ``.de.srt``, ``.en.srt`` and ``.fr.srt`` next to the video. The route walked
  the items one by one and kept only *that item's* language: the de item
  deleted ``.en.srt``, the en item deleted ``.de.srt``. The UI's plain
  ``POST /wanted/cleanup {}`` left only the video — hard-deleted, no trash.
* ``[Group] Show.S01E03.mkv`` matched nothing: the file name went unescaped into
  ``glob``, where ``[Group]`` is a character class.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


@pytest.fixture
def media(client, tmp_path):
    """Point media_path at tmp_path the way the UI would."""
    response = client.put("/api/v1/config", json={"media_path": str(tmp_path)})
    assert response.status_code == 200, response.get_json()
    return tmp_path


def _extracted_item(client, video, lang):
    with client.application.app_context():
        from db.wanted import update_wanted_status, upsert_wanted_item

        row_id, _ = upsert_wanted_item("episode", str(video), title="Show", target_language=lang)
        update_wanted_status(row_id, "extracted")
        return row_id


def test_default_profile_alone_would_not_protect_english(client):
    """Guard for the tests below: they must prove the union of wanted rows, not
    pass because the default profile already lists every language."""
    with client.application.app_context():
        from db.profiles import get_default_profile

        assert "en" not in get_default_profile().get("target_languages", [])


def test_every_wanted_language_of_a_file_survives(client, media):
    video = media / "Show - S01E01.mkv"
    video.write_bytes(b"v")
    for lang in ("de", "en", "fr"):
        (media / f"Show - S01E01.{lang}.srt").write_bytes(_SRT)
    _extracted_item(client, video, "de")
    _extracted_item(client, video, "en")

    trashed = []
    with patch(
        "services.wanted_sidecar_cleanup._trash_path",
        side_effect=lambda p: (trashed.append(p), os.remove(p), True)[-1],
    ):
        response = client.post("/api/v1/wanted/cleanup", json={})

    assert response.status_code == 200, response.get_json()
    assert (media / "Show - S01E01.de.srt").exists()
    assert (media / "Show - S01E01.en.srt").exists()
    assert trashed == [str(media / "Show - S01E01.fr.srt")]


def test_dry_run_reports_the_same_plan_and_touches_nothing(client, media):
    video = media / "Show - S01E02.mkv"
    video.write_bytes(b"v")
    for lang in ("de", "en", "fr"):
        (media / f"Show - S01E02.{lang}.srt").write_bytes(_SRT)
    _extracted_item(client, video, "de")
    _extracted_item(client, video, "en")

    response = client.post("/api/v1/wanted/cleanup", json={"dry_run": True})

    data = response.get_json()
    assert data["deleted"] == [str(media / "Show - S01E02.fr.srt")]
    assert sorted(data["kept"]) == sorted(
        [str(media / "Show - S01E02.de.srt"), str(media / "Show - S01E02.en.srt")]
    )
    assert all((media / f"Show - S01E02.{lang}.srt").exists() for lang in ("de", "en", "fr"))


def test_a_selected_item_does_not_decide_alone_for_its_file(client, media):
    """item_ids narrows which files are cleaned, not which languages are wanted."""
    video = media / "Show - S01E03.mkv"
    video.write_bytes(b"v")
    for lang in ("de", "en"):
        (media / f"Show - S01E03.{lang}.srt").write_bytes(_SRT)
    de_id = _extracted_item(client, video, "de")
    _extracted_item(client, video, "en")

    response = client.post("/api/v1/wanted/cleanup", json={"item_ids": [de_id], "dry_run": True})

    assert response.get_json()["deleted"] == []


def test_removed_sidecars_go_to_the_trash_not_os_remove(client, media):
    video = media / "Show - S01E04.mkv"
    video.write_bytes(b"v")
    (media / "Show - S01E04.fr.srt").write_bytes(_SRT)
    _extracted_item(client, video, "de")

    with (
        patch("services.wanted_sidecar_cleanup._trash_path", return_value=True) as trash,
        patch("os.remove") as remove,
    ):
        response = client.post("/api/v1/wanted/cleanup", json={})

    assert response.status_code == 200
    trash.assert_called_once_with(str(media / "Show - S01E04.fr.srt"))
    remove.assert_not_called()


def test_bracketed_file_names_are_matched(client, media):
    video = media / "[Group] Show.S01E03.mkv"
    video.write_bytes(b"v")
    (media / "[Group] Show.S01E03.de.srt").write_bytes(_SRT)
    (media / "[Group] Show.S01E03.fr.srt").write_bytes(_SRT)
    _extracted_item(client, video, "de")

    response = client.post("/api/v1/wanted/cleanup", json={"dry_run": True})

    data = response.get_json()
    assert data["deleted"] == [str(media / "[Group] Show.S01E03.fr.srt")]
    assert data["kept"] == [str(media / "[Group] Show.S01E03.de.srt")]


def test_unclassifiable_tokens_and_aliases_are_kept(client, media):
    video = media / "Show - S01E05.mkv"
    video.write_bytes(b"v")
    (media / "Show - S01E05.ger.srt").write_bytes(_SRT)  # alias of de
    (media / "Show - S01E05.final.srt").write_bytes(_SRT)  # not a language
    _extracted_item(client, video, "de")

    response = client.post("/api/v1/wanted/cleanup", json={"dry_run": True})

    data = response.get_json()
    assert data["deleted"] == []
    assert str(media / "Show - S01E05.ger.srt") in data["kept"]
    assert str(media / "Show - S01E05.final.srt") in data["kept"]


# ── cold-review findings (Codex, 2026-09-17) ─────────────────────────────────


def test_a_script_variant_target_keeps_its_generic_language(client, media):
    """A zh-hans row must keep .zh/.chi files: containers tag Chinese generically.
    Only the profile languages went through that expansion, row languages did not."""
    video = media / "Show - S02E01.mkv"
    video.write_bytes(b"v")
    for tag in ("zh", "chi", "de"):
        (media / f"Show - S02E01.{tag}.srt").write_bytes(_SRT)
    _extracted_item(client, video, "zh-hans")

    response = client.post("/api/v1/wanted/cleanup", json={"dry_run": True})

    assert response.get_json()["deleted"] == []


def test_an_undetermined_row_language_is_not_a_keep_language(client):
    """A row targeting "und" must not put "und" into the keep set: a keep set of
    just "undetermined" would pass the non-empty guard and arm the cleanup."""
    from unittest.mock import patch as _patch

    from config import get_settings
    from services.wanted_sidecar_cleanup import _wanted_languages

    rows = [{"target_language": "und", "file_path": "/media/x.mkv"}]
    with (
        client.application.app_context(),
        _patch("db.wanted.get_wanted_items_by_path", return_value=rows),
        _patch(
            "services.embedded_extractor.resolve_profile_for_item",
            return_value={"target_languages": []},
        ),
    ):
        assert _wanted_languages("/media/x.mkv", rows, get_settings()) == set()


def test_a_script_variant_row_keeps_the_generic_language(client):
    from unittest.mock import patch as _patch

    from config import get_settings
    from services.wanted_sidecar_cleanup import _wanted_languages

    rows = [{"target_language": "zh-hans", "file_path": "/media/x.mkv"}]
    with (
        client.application.app_context(),
        _patch("db.wanted.get_wanted_items_by_path", return_value=rows),
        _patch(
            "services.embedded_extractor.resolve_profile_for_item",
            return_value={"target_languages": []},
        ),
    ):
        assert _wanted_languages("/media/x.mkv", rows, get_settings()) == {"zh-hans", "zh"}


def test_same_named_sidecars_from_different_folders_all_survive_in_the_trash(client, media):
    """The trash flattens paths to the basename and only added whole seconds on a
    collision — three files trashed within one second could overwrite each other."""
    with client.application.app_context():
        from config import get_settings
        from remux import _resolve_trash_dir

        trash_root = _resolve_trash_dir(str(media / "x.srt"), ".sublarr")
        media_root = get_settings().media_path
    before = {p for p in Path(trash_root).rglob("*.srt")} if os.path.isdir(trash_root) else set()

    contents = []
    for i in range(3):
        folder = media / f"Season {i + 1}"
        folder.mkdir()
        video = folder / "Show - S01E01.mkv"
        video.write_bytes(b"v")
        body = _SRT + f"{i}\n".encode()
        (folder / "Show - S01E01.fr.srt").write_bytes(body)
        contents.append(body)
        _extracted_item(client, video, "de")

    response = client.post("/api/v1/wanted/cleanup", json={})

    assert response.status_code == 200, response.get_json()
    assert len(response.get_json()["deleted"]) == 3, response.get_json()
    assert media_root  # the trash lives under it, wherever the harness points it
    new = {p for p in Path(trash_root).rglob("*.srt")} - before
    try:
        assert len(new) == 3, sorted(p.name for p in new)
        assert sorted(p.read_bytes() for p in new) == sorted(contents)
    finally:
        for p in new:
            p.unlink(missing_ok=True)
