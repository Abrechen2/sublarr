# backend/tests/test_subtitle_processor.py
"""Tests for subtitle_processor — core orchestrator."""

import os
import pytest


def test_apply_mods_returns_processing_result(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Hello world"])
    result = apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES)], dry_run=True)

    assert result.dry_run is True
    assert isinstance(result.changes, list)
    assert result.output_path == path


def test_dry_run_does_not_write_file(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Downloaded from opensubtitles.org"])
    mtime_before = os.path.getmtime(path)

    apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES, options={"watermark_removal": True})], dry_run=True)

    assert os.path.getmtime(path) == mtime_before


def test_backup_created_on_first_run(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Downloaded from opensubtitles.org"])
    base, ext = os.path.splitext(path)
    bak_path = f"{base}.bak{ext}"

    result = apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES, options={"watermark_removal": True})])

    assert result.backed_up is True
    assert os.path.exists(bak_path)


def test_backup_not_overwritten_on_second_run(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Downloaded from opensubtitles.org"])
    base, ext = os.path.splitext(path)
    bak_path = f"{base}.bak{ext}"

    apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES, options={"watermark_removal": True})])
    bak_mtime = os.path.getmtime(bak_path)

    apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES, options={"watermark_removal": True})])

    assert os.path.getmtime(bak_path) == bak_mtime


def test_unsupported_format_raises(tmp_path):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = str(tmp_path / "video.mkv")
    with open(path, "w") as f:
        f.write("not a subtitle")

    with pytest.raises(ValueError, match="Unsupported format"):
        apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES)])


def test_mod_order_enforced(create_test_subtitle):
    """Mods passed in wrong order are still applied in: common_fixes → hi_removal."""
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["[MUSIC] Hello"])
    result = apply_mods(path, [
        ModConfig(mod=ModName.HI_REMOVAL),
        ModConfig(mod=ModName.COMMON_FIXES),
    ], dry_run=True)

    mod_names = [c.mod_name for c in result.changes]
    cf_idx = next((i for i, n in enumerate(mod_names) if n == "common_fixes"), None)
    hi_idx = next((i for i, n in enumerate(mod_names) if n == "hi_removal"), None)
    if cf_idx is not None and hi_idx is not None:
        assert cf_idx < hi_idx


def test_change_has_all_required_fields(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Downloaded from subscene.com"])
    result = apply_mods(path, [ModConfig(mod=ModName.COMMON_FIXES, options={"watermark_removal": True})], dry_run=True)

    assert len(result.changes) >= 1
    c = result.changes[0]
    assert isinstance(c.event_index, int)
    assert "-->" in c.timestamp
    assert isinstance(c.original_text, str)
    assert isinstance(c.modified_text, str)
    assert isinstance(c.mod_name, str)
