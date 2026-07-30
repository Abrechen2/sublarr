"""Tests for the Shoko Server integration.

Covers the ShokoClient parser, the ShokoServer media-server backend
(rescan-after-download), and the authoritative Tier-0 AniDB lookup in the
wanted-search enricher chain.

Run:
    pytest tests/test_shoko_integration.py -v
"""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# ShokoClient — cross-reference parsing
# ---------------------------------------------------------------------------
class TestShokoClientParsing:
    def _client(self):
        from metadata.shoko_client import ShokoClient

        return ShokoClient(url="http://shoko:8111", api_key="key123")

    def test_get_file_ids_nested_shape(self):
        client = self._client()
        file_obj = {
            "ID": 42,
            "SeriesIDs": [
                {
                    "SeriesID": {"ID": 7, "AniDB": 6789},
                    "EpisodeIDs": [{"ID": 15, "AniDB": 112233}],
                }
            ],
        }
        client._get = MagicMock(
            side_effect=lambda path, params=None, **kw: (
                [file_obj]
                if path == "/api/v3/File/PathEndsWith"
                else {"AniDB": {"Type": "Normal", "EpisodeNumber": 5}}
            )
        )

        ids = client.get_file_ids_by_path("/anime/Show/Show - 05.mkv")

        assert ids is not None
        assert ids.file_id == 42
        assert ids.anidb_anime_id == 6789
        assert ids.anidb_episode_id == 112233
        assert ids.absolute_episode == 5

    def test_get_file_ids_flat_shape(self):
        client = self._client()
        file_obj = {
            "ID": 1,
            "SeriesIDs": [{"AnidbAnimeID": 555, "AnidbEpisodeID": 999}],
        }
        client._get = MagicMock(return_value=[file_obj])

        ids = client.get_file_ids_by_path("/anime/x.mkv")

        assert ids.anidb_anime_id == 555
        assert ids.anidb_episode_id == 999
        # No Shoko episode ID in flat shape -> no absolute lookup attempted.
        assert ids.absolute_episode is None

    def test_get_file_ids_unknown_file_returns_none(self):
        client = self._client()
        client._get = MagicMock(return_value=[])

        assert client.get_file_ids_by_path("/anime/missing.mkv") is None

    def test_get_file_ids_empty_path_returns_none(self):
        client = self._client()
        assert client.get_file_ids_by_path("") is None

    def test_special_episode_has_no_absolute_number(self):
        client = self._client()
        file_obj = {
            "ID": 3,
            "SeriesIDs": [{"SeriesID": {"AniDB": 1}, "EpisodeIDs": [{"ID": 9, "AniDB": 2}]}],
        }
        client._get = MagicMock(
            side_effect=lambda path, params=None, **kw: (
                [file_obj]
                if path == "/api/v3/File/PathEndsWith"
                else {"AniDB": {"Type": "Special", "EpisodeNumber": 3}}
            )
        )

        ids = client.get_file_ids_by_path("/anime/Show/Special.mkv")

        assert ids.anidb_anime_id == 1
        assert ids.absolute_episode is None  # specials excluded

    def test_rescan_file_by_path(self):
        client = self._client()
        client.get_file_ids_by_path = MagicMock(return_value=_ids(file_id=42, anime=1, episode=2))
        client._post = MagicMock(return_value={})

        assert client.rescan_file_by_path("/anime/x.mkv") is True
        client._post.assert_called_once_with("/api/v3/File/42/Rescan")

    def test_rescan_file_unknown_returns_false(self):
        client = self._client()
        client.get_file_ids_by_path = MagicMock(return_value=None)

        assert client.rescan_file_by_path("/anime/x.mkv") is False

    def test_refresh_library_scans_all_folders(self):
        client = self._client()
        calls = []

        def fake_get(path, params=None, **kw):
            calls.append(path)
            if path == "/api/v3/ImportFolder":
                return [{"ID": 1}, {"ID": 2}]
            return {}

        client._get = MagicMock(side_effect=fake_get)

        assert client.refresh_library() is True
        assert "/api/v3/ImportFolder/1/Scan" in calls
        assert "/api/v3/ImportFolder/2/Scan" in calls


# ---------------------------------------------------------------------------
# ShokoClient — auth + health
# ---------------------------------------------------------------------------
class TestShokoClientAuth:
    def test_api_key_sets_header(self):
        from metadata.shoko_client import ShokoClient

        client = ShokoClient(url="http://shoko:8111", api_key="abc")
        assert client.session.headers.get("apikey") == "abc"
        assert client._ensure_auth() is True

    def test_ensure_auth_without_credentials_is_false(self):
        from metadata.shoko_client import ShokoClient

        client = ShokoClient(url="http://shoko:8111")
        assert client._ensure_auth() is False

    def test_ensure_auth_logs_in_with_user_pass(self):
        from metadata.shoko_client import ShokoClient

        client = ShokoClient(url="http://shoko:8111", username="u", password="p")
        resp = MagicMock()
        resp.json.return_value = {"apikey": "fresh-key"}
        resp.raise_for_status.return_value = None
        with patch.object(client.session, "post", return_value=resp) as post:
            assert client._ensure_auth() is True
        assert client.session.headers.get("apikey") == "fresh-key"
        assert post.call_args.args[0] == "http://shoko:8111/api/auth"

    def test_health_check_unreachable(self):
        from metadata.shoko_client import ShokoClient

        client = ShokoClient(url="http://shoko:8111", api_key="abc")
        client._get = MagicMock(return_value=None)

        ok, msg = client.health_check()
        assert ok is False
        assert "Cannot connect" in msg

    def test_health_check_ok(self):
        from metadata.shoko_client import ShokoClient

        client = ShokoClient(url="http://shoko:8111", api_key="abc")
        client._get = MagicMock(
            side_effect=lambda path, params=None, **kw: (
                {"State": "Started"} if "Init/Status" in path else {"ok": True}
            )
        )

        ok, msg = client.health_check()
        assert ok is True
        assert "Connected to Shoko" in msg


# ---------------------------------------------------------------------------
# ShokoServer media-server backend
# ---------------------------------------------------------------------------
class TestShokoServer:
    def test_registered_in_manager(self):
        from mediaserver import get_media_server_manager, invalidate_media_server_manager

        invalidate_media_server_manager()
        manager = get_media_server_manager()
        names = {t["name"] for t in manager.get_all_server_types()}
        assert "shoko" in names

    def test_refresh_item_success(self):
        from mediaserver.shoko import ShokoServer

        server = ShokoServer(url="http://shoko:8111", api_key="k", name="My Shoko")
        fake_client = MagicMock()
        fake_client.rescan_file_by_path.return_value = True
        server._client = MagicMock(return_value=fake_client)

        result = server.refresh_item("/media/anime/ep.mkv", "episode")

        assert result.success is True
        fake_client.rescan_file_by_path.assert_called_once_with("/media/anime/ep.mkv")

    def test_refresh_item_falls_back_to_library(self):
        from mediaserver.shoko import ShokoServer

        server = ShokoServer(url="http://shoko:8111", api_key="k")
        fake_client = MagicMock()
        fake_client.rescan_file_by_path.return_value = False
        fake_client.refresh_library.return_value = True
        server._client = MagicMock(return_value=fake_client)

        result = server.refresh_item("/media/anime/ep.mkv")

        assert result.success is True
        fake_client.refresh_library.assert_called_once()

    def test_refresh_item_applies_path_mapping(self):
        from mediaserver.shoko import ShokoServer

        server = ShokoServer(url="http://shoko:8111", api_key="k", path_mapping="/media:/data")
        fake_client = MagicMock()
        fake_client.rescan_file_by_path.return_value = True
        server._client = MagicMock(return_value=fake_client)

        server.refresh_item("/media/anime/ep.mkv")

        fake_client.rescan_file_by_path.assert_called_once_with("/data/anime/ep.mkv")

    def test_health_check_delegates_to_client(self):
        from mediaserver.shoko import ShokoServer

        server = ShokoServer(url="http://shoko:8111", api_key="k")
        fake_client = MagicMock()
        fake_client.health_check.return_value = (True, "ok")
        server._client = MagicMock(return_value=fake_client)

        assert server.health_check() == (True, "ok")


# ---------------------------------------------------------------------------
# Enricher — Tier-0 Shoko AniDB resolution
# ---------------------------------------------------------------------------
class TestShokoEnricher:
    def _query(self, file_path="/anime/Show/Show - 05.mkv"):
        from providers.base import VideoQuery

        return VideoQuery(file_path=file_path)

    def test_noop_when_no_shoko_config(self):
        from wanted_search.metadata_enrichers import _resolve_anidb_from_shoko

        query = self._query()
        with patch("config.get_shoko_config", return_value=None):
            assert _resolve_anidb_from_shoko(query) is False
        assert query.anidb_id is None

    def test_noop_when_no_file_path(self):
        from wanted_search.metadata_enrichers import _resolve_anidb_from_shoko

        query = self._query(file_path="")
        assert _resolve_anidb_from_shoko(query) is False

    def test_sets_ids_from_shoko(self):
        from wanted_search.metadata_enrichers import _resolve_anidb_from_shoko

        query = self._query()
        fake_client = MagicMock()
        fake_client.get_file_ids_by_path.return_value = _ids(
            file_id=42, anime=6789, episode=112233, absolute=5
        )
        with (
            patch("config.get_shoko_config", return_value={"url": "http://shoko:8111"}),
            patch("metadata.shoko_client.ShokoClient", return_value=fake_client),
        ):
            assert _resolve_anidb_from_shoko(query) is True

        assert query.anidb_id == 6789
        assert query.anidb_episode_id == 112233
        assert query.absolute_episode == 5

    def test_returns_false_when_file_unknown_to_shoko(self):
        from wanted_search.metadata_enrichers import _resolve_anidb_from_shoko

        query = self._query()
        fake_client = MagicMock()
        fake_client.get_file_ids_by_path.return_value = None
        with (
            patch("config.get_shoko_config", return_value={"url": "http://shoko:8111"}),
            patch("metadata.shoko_client.ShokoClient", return_value=fake_client),
        ):
            assert _resolve_anidb_from_shoko(query) is False
        assert query.anidb_id is None

    def test_shoko_wins_as_tier0_in_standalone_chain(self):
        """When Shoko resolves, the fuzzy cache/AniList/title tiers are skipped."""
        from providers.base import VideoQuery
        from wanted_search.metadata_enrichers import _resolve_anidb_id_for_standalone

        query = VideoQuery(file_path="/anime/x.mkv", tvdb_id=100, anilist_id=200)
        fake_client = MagicMock()
        fake_client.get_file_ids_by_path.return_value = _ids(file_id=1, anime=333, episode=444)
        with (
            patch("config.get_shoko_config", return_value={"url": "http://shoko:8111"}),
            patch("metadata.shoko_client.ShokoClient", return_value=fake_client),
            patch("db.cache.get_anidb_mapping") as cache_lookup,
        ):
            _resolve_anidb_id_for_standalone(query, {"id": 1})

        assert query.anidb_id == 333
        cache_lookup.assert_not_called()  # fuzzy chain never reached


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ids(file_id=None, anime=None, episode=None, absolute=None):
    from metadata.shoko_client import ShokoFileIDs

    return ShokoFileIDs(
        file_id=file_id,
        anidb_anime_id=anime,
        anidb_episode_id=episode,
        absolute_episode=absolute,
    )
