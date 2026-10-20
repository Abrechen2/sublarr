"""Bring back the letters that the UTF-8-with-replacement decode destroyed.

Before the encoding fix, a cp1252/cp1251/... download reached disk with every
non-ASCII letter replaced by U+FFFD. The letters are gone from the file, so the
only way back is the provider's original. Proof per cue: the "�" runs of the
file on disk are a mask — the ASCII around them must match the re-downloaded,
correctly decoded cue exactly. Cues edited since (sync keeps the text, HI
removal does not) simply do not match and are left alone.
"""

import io
from unittest.mock import patch

import pysubs2
import pytest

from services.repair.encoding_restore import (
    NOTHING_TO_RESTORE,
    has_mangled_letters,
    restore_encoding,
)
from services.repair.restore import RestoreRefusedError


def _srt(cues) -> bytes:
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    return buf.getvalue().encode("utf-8")


ORIGINAL = _srt(
    [
        (1000, 3000, "Grüße aus München!"),
        (4000, 6000, "Das Mädchen läuft über die Brücke."),
        (7000, 9000, "Alles klar."),
    ]
)


def _mangled(raw_utf8: bytes, encoding: str = "cp1252") -> bytes:
    """What the old pipeline wrote for this subtitle delivered in ``encoding``."""
    legacy = raw_utf8.decode("utf-8").encode(encoding)
    return legacy.decode("utf-8", errors="replace").encode("utf-8")


def _texts(raw: bytes) -> list[str]:
    return [e.text for e in pysubs2.SSAFile.from_string(raw.decode("utf-8")).events]


def test_detects_mangled_letters():
    assert has_mangled_letters(_mangled(ORIGINAL))
    assert not has_mangled_letters(ORIGINAL)


def test_restores_every_cue():
    out = restore_encoding(original=ORIGINAL, on_disk=_mangled(ORIGINAL), fmt="srt")
    assert _texts(out) == _texts(ORIGINAL)


def test_keeps_the_timings_on_disk():
    # Synced after download: the times on disk win, only the letters come back.
    synced = _srt(
        [
            (1500, 3500, "Grüße aus München!"),
            (4500, 6500, "Das Mädchen läuft über die Brücke."),
            (7500, 9500, "Alles klar."),
        ]
    )
    out = restore_encoding(original=ORIGINAL, on_disk=_mangled(synced), fmt="srt")
    events = pysubs2.SSAFile.from_string(out.decode("utf-8")).events
    assert [e.start for e in events] == [1500, 4500, 7500]
    assert events[0].text == "Grüße aus München!"


def test_an_edited_cue_is_left_alone():
    on_disk = _mangled(ORIGINAL).replace(b"aus M", b"von M")
    out = restore_encoding(original=ORIGINAL, on_disk=on_disk, fmt="srt")
    texts = _texts(out)
    assert "�" in texts[0]  # no proof for this one
    assert texts[1] == "Das Mädchen läuft über die Brücke."


def test_cyrillic():
    original = _srt([(1000, 2000, "Привет, как дела?"), (3000, 4000, "Всё хорошо.")])
    on_disk = _mangled(original, "cp1251")
    out = restore_encoding(original=original, on_disk=on_disk, fmt="srt", language="ru")
    assert _texts(out) == _texts(original)


def test_ass_dialogue():
    original = (
        "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\i1}Grüße{\\i0} aus München\n"
    ).encode()
    out = restore_encoding(original=original, on_disk=_mangled(original), fmt="ass")
    assert "{\\i1}Grüße{\\i0} aus München" in out.decode("utf-8")


def test_refuses_another_subtitle():
    other = _srt([(1000, 3000, "Völlig andere Übersetzung.")])
    with pytest.raises(RestoreRefusedError, match="no cue"):
        restore_encoding(original=other, on_disk=_mangled(ORIGINAL), fmt="srt")


def test_refuses_an_original_that_still_has_replacement_characters():
    broken = ORIGINAL.replace("ü".encode(), "�".encode())
    with pytest.raises(RestoreRefusedError, match="original"):
        restore_encoding(original=broken, on_disk=_mangled(ORIGINAL), fmt="srt")


def test_nothing_to_restore_on_a_clean_file():
    with pytest.raises(RestoreRefusedError, match=NOTHING_TO_RESTORE):
        restore_encoding(original=ORIGINAL, on_disk=ORIGINAL, fmt="srt")


def test_ambiguous_mask_is_not_guessed():
    # "M�dchen" fits both "Mädchen" and "Mödchen": no proof which one it was.
    original = _srt([(1000, 2000, "Mädchen"), (3000, 4000, "Mödchen")])
    on_disk = _srt([(1000, 2000, "M�dchen")])
    with pytest.raises(RestoreRefusedError, match="no cue"):
        restore_encoding(original=original, on_disk=on_disk, fmt="srt")


def test_same_position_resolves_an_otherwise_ambiguous_mask():
    original = _srt([(1000, 2000, "Mädchen"), (3000, 4000, "Mödchen")])
    on_disk = _mangled(original)
    out = restore_encoding(original=original, on_disk=on_disk, fmt="srt")
    assert _texts(out) == ["Mädchen", "Mödchen"]


# -- the runner ------------------------------------------------------------------


@pytest.fixture
def mangled_candidate(tmp_path):
    from services.repair.runner import RepairCandidate

    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(_mangled(ORIGINAL))
    return RepairCandidate(
        file_path=str(path),
        language="de",
        fmt="srt",
        original_hash="irrelevant",
        provider="opensubtitles",
        subtitle_id="42",
        kind="encoding",
    )


def test_runner_restores_an_encoding_candidate(app_ctx, mangled_candidate):
    from services.repair.runner import repair_one

    with (
        patch("services.repair.runner.fetch_original", return_value=ORIGINAL),
        patch("services.repair.runner._record_repair") as record,
    ):
        outcome = repair_one(mangled_candidate)
    assert outcome.status == "repaired"
    assert "Grüße aus München!" in open(mangled_candidate.file_path, encoding="utf-8").read()
    record.assert_called_once()


def test_runner_never_uses_the_bak_for_an_encoding_candidate(app_ctx, mangled_candidate):
    # The .bak was copied from the mangled file: its letters are gone too.
    from services.repair.runner import obtain_original

    with (
        patch("services.repair.runner._pristine_bak", return_value=b"bak") as bak,
        patch("services.repair.runner.fetch_original", return_value=ORIGINAL),
    ):
        original, source = obtain_original(mangled_candidate)
    bak.assert_not_called()
    assert (original, source) == (ORIGINAL, "provider")


def test_runner_dry_run_writes_nothing(app_ctx, mangled_candidate):
    from services.repair.runner import repair_one

    before = open(mangled_candidate.file_path, "rb").read()
    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL):
        outcome = repair_one(mangled_candidate, dry_run=True)
    assert outcome.status == "repaired"
    assert open(mangled_candidate.file_path, "rb").read() == before


# -- the scanner -----------------------------------------------------------------


def _scan_with(tmp_path, files):
    """Run scanner.scan over ``files`` ({name: (bytes, stored_hash)})."""
    from unittest.mock import MagicMock

    from services.repair import scanner

    rows = []
    for name, (raw, stored) in files.items():
        path = tmp_path / name
        path.write_bytes(raw)
        rows.append((str(path), stored, "de", "srt"))
    index = {(str(tmp_path / "Show - S01E01"), "de"): ("opensubtitles", "42")}
    result = MagicMock()
    result.fetchall.return_value = rows
    with (
        patch.object(scanner.db.session, "execute", return_value=result),
        patch.object(scanner, "_download_index", return_value=index),
        patch.object(scanner, "_repaired_paths", return_value={}),
    ):
        return scanner.scan()


def test_scan_picks_up_mangled_files_even_with_an_untouched_hash(app_ctx, tmp_path):
    from services.repair.scanner import content_hash

    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(_mangled(ORIGINAL))
    stored = content_hash(str(path))  # the hash was taken of the mangled file
    report = _scan_with(tmp_path, {"Show - S01E01.de.srt": (_mangled(ORIGINAL), stored)})
    assert [c.kind for c in report.candidates] == ["encoding"]
    assert report.untouched == 0


def test_scan_leaves_clean_untouched_files_alone(app_ctx, tmp_path):
    from services.repair.scanner import content_hash

    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ORIGINAL)
    report = _scan_with(tmp_path, {"Show - S01E01.de.srt": (ORIGINAL, content_hash(str(path)))})
    assert report.candidates == []
    assert report.untouched == 1


def test_download_index_works_on_sqlite(app_ctx, tmp_path):
    """The scan used Postgres-only DISTINCT ON and failed on every SQLite install."""
    from db.providers import record_subtitle_download
    from services.repair.scanner import _download_index

    video = str(tmp_path / "Show - S01E01.mkv")
    record_subtitle_download("opensubtitles", "old", "de", "srt", video, 90)
    record_subtitle_download("subdl", "new", "de", "srt", video, 95)
    record_subtitle_download("opensubtitles", "en-1", "en", "srt", video, 90)

    index = _download_index("de")

    assert index == {(str(tmp_path / "Show - S01E01"), "de"): ("subdl", "new")}
    assert _download_index(None)[(str(tmp_path / "Show - S01E01"), "en")] == (
        "opensubtitles",
        "en-1",
    )
