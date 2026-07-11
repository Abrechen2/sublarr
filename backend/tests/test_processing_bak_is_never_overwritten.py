"""The processing .bak is a single-slot undo — it must never be re-created.

``apply_mods`` only writes a backup when none exists, but it checked the
*canonical* path alone (``bak_path_for`` → ``<dir>/.sublarr/backups/``). Backups
used to live next to the sidecar. After they were moved, every pre-migration
file looked un-backed-up, so the next processing run happily created a "pristine"
backup — from a file that had already been mangled by the pipeline.

That is how the only record of the original text was destroyed: on the
production library the .bak files turned out to be byte-identical to the damaged
sidecars. ``find_existing_bak`` knows both locations; use it.
"""

import os
import shutil

import pysubs2


def _write_srt(path, lines):
    subs = pysubs2.SSAFile()
    for i, line in enumerate(lines):
        subs.events.append(
            pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=line)
        )
    subs.save(str(path), format_="srt", encoding="utf-8")


def test_legacy_bak_is_not_shadowed_by_a_fresh_one(tmp_path):
    """A backup at the LEGACY sibling path must count as "already backed up"."""
    from subtitle_filename import bak_path_for, legacy_bak_path_for
    from subtitle_processor import ModConfig, ModName, apply_mods

    sidecar = tmp_path / "Show - S01E01.de.srt"
    _write_srt(sidecar, ["[DOOR SLAMS] Guten Morgen."])

    # The pristine original, backed up before the backup location moved.
    legacy = legacy_bak_path_for(str(sidecar))
    os.makedirs(os.path.dirname(legacy), exist_ok=True)
    shutil.copyfile(str(sidecar), legacy)
    pristine = open(legacy, encoding="utf-8").read()

    result = apply_mods(str(sidecar), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)

    assert result.changes, "sanity: the pipeline must have modified the sidecar"
    assert result.backed_up is False, "a bak already exists — none may be written"
    assert not os.path.exists(bak_path_for(str(sidecar))), (
        "a second backup was created at the canonical path, shadowing the pristine one"
    )
    assert open(legacy, encoding="utf-8").read() == pristine, "the pristine backup was overwritten"


def test_first_run_still_creates_a_backup(tmp_path):
    """With no backup anywhere, the pre-processing state is captured as usual."""
    from subtitle_filename import find_existing_bak
    from subtitle_processor import ModConfig, ModName, apply_mods

    sidecar = tmp_path / "Show - S01E02.de.srt"
    _write_srt(sidecar, ["[DOOR SLAMS] Guten Morgen."])
    original = open(str(sidecar), encoding="utf-8").read()

    result = apply_mods(str(sidecar), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)

    assert result.backed_up is True
    bak = find_existing_bak(str(sidecar))
    assert bak is not None
    assert open(bak, encoding="utf-8").read() == original, "the bak must hold the PRE-edit content"
