"""Tests that the AniDB title-index build never runs in the search hot path.

Task 5: resolve_anidb_from_title_dump() must only ever *serve* the in-memory
_title_index; building it (download + defusedxml parse of the offline dump,
tens of seconds of GIL-held CPU on low-power hosts) is the exclusive job of
warm_title_index(), called from the anidb_sync scheduler tick and a daemon
warm thread at startup.
"""

from unittest.mock import patch


def test_hot_path_never_builds_index():
    import anidb_mapper

    with (
        patch.object(anidb_mapper, "_title_index", {}),
        patch.object(
            anidb_mapper, "_fetch_dump", side_effect=AssertionError("hot path downloaded")
        ),
    ):
        assert anidb_mapper.resolve_anidb_from_title_dump("One Piece") is None


def test_warm_title_index_builds(tmp_path, monkeypatch):
    import gzip

    import anidb_mapper

    dump = tmp_path / "anime-titles.xml.gz"
    xml = b'<animetitles><anime aid="69"><title>One Piece</title></anime></animetitles>'
    with gzip.open(dump, "wb") as f:
        f.write(xml)

    monkeypatch.setattr(anidb_mapper, "_DUMP_CACHE_FILE", str(dump))
    monkeypatch.setattr(anidb_mapper, "_title_index", {})
    monkeypatch.setattr(anidb_mapper, "_title_index_loaded_at", 0.0)

    anidb_mapper.warm_title_index()
    assert anidb_mapper.resolve_anidb_from_title_dump("One Piece") == 69
