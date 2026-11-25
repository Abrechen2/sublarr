"""A forced/HI download does not hide the machine-translated main subtitle (#51).

Provenance was decided by the latest download row for video + language +
format. A forced subtitle saved later in the same language and format is a
different file, but its genuine row made the machine-translated full sidecar
read as genuine: the re-seek stopped looking for an original.
"""

from __future__ import annotations


def _repo():
    from db.repositories.providers import ProviderRepository

    return ProviderRepository()


def _record(repo, source, subtitle_type):
    repo.record_subtitle_download(
        "p", "id", "de", "ass", "/media/ep.mkv", 100, source=source, subtitle_type=subtitle_type
    )


def test_later_forced_row_does_not_hide_the_full_translation(app_ctx):
    repo = _repo()
    _record(repo, "machine_translation", "full")
    _record(repo, "provider", "forced")

    assert repo.is_machine_translated("/media/ep.mkv", "de", "ass") is True
    assert ("/media/ep.mkv", "de", "ass") in repo.list_machine_translations()


def test_forced_translation_is_judged_on_its_own_history(app_ctx):
    repo = _repo()
    _record(repo, "provider", "full")
    _record(repo, "machine_translation", "forced")

    assert repo.is_machine_translated("/media/ep.mkv", "de", "ass") is False
    assert repo.is_machine_translated("/media/ep.mkv", "de", "ass", subtitle_type="forced")
    assert ("/media/ep.mkv", "de", "ass") not in repo.list_machine_translations()


def test_genuine_full_download_still_replaces_the_translation(app_ctx):
    repo = _repo()
    _record(repo, "machine_translation", "full")
    _record(repo, "provider", "full")

    assert repo.is_machine_translated("/media/ep.mkv", "de", "ass") is False
