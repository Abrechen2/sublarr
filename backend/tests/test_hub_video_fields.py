"""The video dict carries what the pinned catalog bundles gate their search on.

Issue #220: TsukiHime, CinemaZ and AvistaZ returned nothing for every file,
because ``video_from_query`` never set the keys their ``search`` checks first
(``series_anidb_episode_no``, the movie ``anilist_id``, ``info_url``), and the
fps-aware bundles never saw an ``fps``. The vendored bundles are loaded here
for real — only their HTTP layer is stubbed — so a key renamed on either side
fails a test instead of silently emptying a provider.
"""

import pytest

from providers.base import VideoQuery
from providers.hub import _load_impl, discover_bundles
from providers.hub.adapter import video_from_query

_GERMAN = [{"alpha2": "de", "alpha3": "ger"}]


def _impl(hub_id: str):
    bundles = {bundle_id: (path, manifest) for bundle_id, path, manifest in discover_bundles()}
    path, manifest = bundles[hub_id]
    return _load_impl(hub_id, path, manifest)()


def _episode(**overrides):
    base = dict(
        series_title="Frieren",
        season=1,
        episode=2,
        languages=["de"],
        file_path="/anime/Frieren/S01/Frieren - S01E02.mkv",
    )
    base.update(overrides)
    return VideoQuery(**base)


def _movie(**overrides):
    base = dict(title="Suzume", year=2022, languages=["de"], file_path="/movies/Suzume.mkv")
    base.update(overrides)
    return VideoQuery(**base)


# -- the dict itself -----------------------------------------------------------


def test_the_anidb_episode_number_is_the_absolute_episode_when_one_is_known():
    video = video_from_query(_episode(season=2, episode=3, absolute_episode=15))
    assert video["series_anidb_episode_no"] == 15


def test_the_anidb_episode_number_falls_back_to_the_episode():
    assert video_from_query(_episode())["series_anidb_episode_no"] == 2


def test_a_movie_carries_its_anilist_id():
    assert video_from_query(_movie(anilist_id=142770))["anilist_id"] == 142770


def test_the_release_page_and_fps_reach_both_kinds():
    for query in (
        _episode(info_url="https://x/t/1", fps=23.976),
        _movie(info_url="https://x/t/1", fps=23.976),
    ):
        video = video_from_query(query)
        assert video["info_url"] == "https://x/t/1"
        assert video["fps"] == 23.976


def test_an_unknown_release_page_and_fps_stay_none():
    video = video_from_query(_episode())
    assert video["info_url"] is None
    assert video["fps"] is None


# -- the pinned bundles read those keys ----------------------------------------


def test_tsukihime_queries_the_episode_by_its_anidb_number():
    impl = _impl("tsukihime")
    calls = []

    def fake_get_json(path):
        calls.append(path)
        return {"id": 77} if path.startswith("/animes/anidb/") else []

    impl._get_json = fake_get_json
    query = _episode(anidb_id=17617, anidb_episode_id=271234, absolute_episode=14)
    assert impl.search(video_from_query(query), _GERMAN, {}) == []
    assert calls == ["/animes/anidb/17617", "/animes/77/episodes/14"]


def test_tsukihime_finds_a_movie_by_its_anilist_id():
    impl = _impl("tsukihime")
    calls = []

    def fake_get_json(path):
        calls.append(path)
        return {"id": 5} if path.startswith("/animes/anilist/") else []

    impl._get_json = fake_get_json
    impl.search(video_from_query(_movie(anilist_id=142770)), _GERMAN, {})
    assert calls == ["/animes/anilist/142770", "/animes/5"]


@pytest.mark.parametrize(
    ("hub_id", "url"),
    [
        ("cinemaz", "https://cinemaz.to/movie/123-suzume"),
        ("avistaz", "https://avistaz.to/torrent/123-suzume"),
    ],
)
def test_the_tracker_bundles_fetch_the_release_page_they_are_given(hub_id, url):
    impl = _impl(hub_id)
    impl._ensure_cookies = lambda cookies, config: None
    fetched = []

    def fake_http_get(target, headers, cookies, timeout=None, **_kw):
        fetched.append(target)
        return type("Resp", (), {"status": 404, "body": b"", "headers": {}})()

    impl._http_get = fake_http_get
    video = video_from_query(_movie(info_url=url))
    assert impl.search(video, _GERMAN, {"cookies": "sid=abc"}) == []
    assert fetched == [url]
