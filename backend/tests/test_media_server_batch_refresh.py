"""The foreign-track sweep refreshes media servers once per slice (night review I1).

The sweep called ``notify_media_servers`` synchronously for every rewritten
file inside its slice loop: up to ~60 s per server per file, and Jellyfin/Plex/
Shoko fall back to a FULL library refresh whenever their per-item search
misses — thousands of library scans over one sweep. The sweep now collects the
rewritten paths and refreshes once at the end of the slice; a per-item miss is
reported instead of falling back, and each server gets at most ONE library
refresh per slice. The download and drain paths keep ``refresh_all``.
"""

from unittest.mock import MagicMock, patch

from mediaserver.base import MediaServer, RefreshResult


class _FakeServer(MediaServer):
    name = "fake"

    def __init__(self, known=(), fail=False, **config):
        super().__init__(**config)
        self.known = set(known)
        self.fail = fail
        self.items = []
        self.fallback_args = []
        self.libraries = 0

    def health_check(self):
        return True, "ok"

    def refresh_item(self, file_path, item_type="", library_fallback=True):
        self.items.append(file_path)
        self.fallback_args.append(library_fallback)
        if self.fail:
            return RefreshResult(success=False, message="connection refused")
        if file_path in self.known:
            return RefreshResult(success=True, message=f"refreshed {file_path}")
        if library_fallback:
            return self.refresh_library()
        return RefreshResult(success=False, message="not found", needs_library_refresh=True)

    def refresh_library(self):
        self.libraries += 1
        return RefreshResult(success=True, message="library refresh")


def _manager(*servers):
    from mediaserver import MediaServerManager

    manager = MediaServerManager()
    for idx, server in enumerate(servers):
        manager._instances[f"fake_{idx}"] = server
        manager._instance_enabled[f"fake_{idx}"] = True
    return manager


def test_misses_in_one_batch_cost_one_library_refresh_per_server():
    server = _FakeServer(known={"/m/a.mkv"})
    _manager(server).refresh_all_batch(["/m/a.mkv", "/m/b.mkv", "/m/c.mkv"])
    assert server.items == ["/m/a.mkv", "/m/b.mkv", "/m/c.mkv"]
    assert server.fallback_args == [False, False, False]
    assert server.libraries == 1


def test_no_library_refresh_when_every_item_was_found():
    server = _FakeServer(known={"/m/a.mkv", "/m/b.mkv"})
    _manager(server).refresh_all_batch(["/m/a.mkv", "/m/b.mkv"])
    assert server.libraries == 0


def test_a_large_batch_is_one_library_refresh_and_no_item_calls():
    from mediaserver import BATCH_ITEM_REFRESH_LIMIT

    server = _FakeServer()
    paths = [f"/m/{i}.mkv" for i in range(BATCH_ITEM_REFRESH_LIMIT + 1)]
    _manager(server).refresh_all_batch(paths)
    assert server.items == []
    assert server.libraries == 1


def test_a_failing_server_is_not_asked_again_within_the_batch():
    """A dead server costs one timeout per slice, not one per file."""
    dead = _FakeServer(fail=True)
    alive = _FakeServer(known={"/m/a.mkv", "/m/b.mkv"})
    results = _manager(dead, alive).refresh_all_batch(["/m/a.mkv", "/m/b.mkv"])
    assert dead.items == ["/m/a.mkv"]
    assert dead.libraries == 0
    assert alive.items == ["/m/a.mkv", "/m/b.mkv"]
    assert any(not r.success for r in results)


def test_the_batch_notifier_deduplicates_and_never_raises():
    from services.media_server_notify import notify_media_servers_batch

    manager = MagicMock()
    manager.refresh_all_batch.return_value = [RefreshResult(success=True, message="ok")]
    with patch("mediaserver.get_media_server_manager", return_value=manager):
        notify_media_servers_batch(["/m/a.mkv", "", "/m/a.mkv", "/m/b.mkv"])
    manager.refresh_all_batch.assert_called_once_with(["/m/a.mkv", "/m/b.mkv"])

    with patch("mediaserver.get_media_server_manager", side_effect=RuntimeError("boom")):
        notify_media_servers_batch(["/m/a.mkv"])  # must not raise

    with patch("mediaserver.get_media_server_manager") as gm:
        notify_media_servers_batch([])
    gm.assert_not_called()


# --- the adapters report a miss instead of scanning the whole library -----------


def test_jellyfin_reports_a_miss_without_a_library_refresh():
    from mediaserver.jellyfin import JellyfinEmbyServer

    server = JellyfinEmbyServer(url="http://jf", api_key="k")
    with (
        patch.object(server, "_search_item_by_path", return_value=None),
        patch.object(server, "refresh_library") as library,
    ):
        result = server.refresh_item("/m/a.mkv", library_fallback=False)
        assert result.needs_library_refresh is True
        library.assert_not_called()
        server.refresh_item("/m/a.mkv")  # the default keeps the fallback
        library.assert_called_once()


def test_shoko_reports_a_miss_without_a_library_refresh():
    from mediaserver.shoko import ShokoServer

    server = ShokoServer(url="http://shoko", api_key="k")
    client = MagicMock()
    client.rescan_file_by_path.return_value = False
    with (
        patch.object(server, "_client", return_value=client),
        patch.object(server, "refresh_library") as library,
    ):
        result = server.refresh_item("/m/a.mkv", library_fallback=False)
        assert result.needs_library_refresh is True
        library.assert_not_called()


def test_plex_reports_a_miss_without_a_library_refresh():
    from mediaserver.plex import PlexServer

    server = PlexServer(url="http://plex", token="t")
    section = MagicMock(type="show", title="Anime")
    plex = MagicMock()
    plex.library.sections.return_value = [section]
    with (
        patch.object(server, "_get_server", return_value=plex),
        patch.object(server, "_find_item_in_section", return_value=None),
        patch.object(server, "refresh_library") as library,
    ):
        result = server.refresh_item("/m/a.mkv", library_fallback=False)
        assert result.needs_library_refresh is True
        library.assert_not_called()


def test_kodi_accepts_the_batch_call():
    from mediaserver.kodi import KodiServer

    server = KodiServer(url="http://kodi")
    with patch.object(server, "_rpc") as rpc:
        assert server.refresh_item("/m/show/a.mkv", library_fallback=False).success
    rpc.assert_called_once_with("VideoLibrary.Scan", {"directory": "/m/show/"})
