"""Final-review I5, I4 and I7 at the policy layer.

I5: a resolution error is not the global policy. ``resolve_policy`` returns
None and every caller treats that as "do not strip now".
I4: a title Sonarr/Radarr confirms missing is skipped; only an unreachable
arr (or an unresolvable policy) makes the override set incomplete, and the
failing ids are named.
I7: a series/movie with ``cleanup_foreign_tracks=False`` is an excluded
folder for the sweep.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from services.foreign_tracks.select import TrackPolicy


def _boom(*_a, **_kw):
    raise RuntimeError("inheritance resolver exploded")


def _add_series(series_id, **fields):
    from db.models.core import SeriesSettings
    from extensions import db

    db.session.add(
        SeriesSettings(sonarr_series_id=series_id, updated_at=datetime.now(UTC), **fields)
    )
    db.session.commit()


def _add_movie(movie_id, **fields):
    from db.models.core import MovieSettings
    from extensions import db

    db.session.add(MovieSettings(radarr_movie_id=movie_id, updated_at=datetime.now(UTC), **fields))
    db.session.commit()


class _Arr:
    """A fake arr client. ``answers`` maps a title id to its folder (HTTP 200)
    or to an HTTP status (e.g. 500); ``None`` means no answer at all
    (connection error/timeout); an id not listed answers 404.

    ``get_*_by_id`` keeps the real clients' lossy semantics (None for every
    non-200) and ``health_check`` always answers, so a policy that still
    trusted "None + healthy" would read an outage as "missing".
    """

    def __init__(self, answers, healthy=True, raise_for=()):
        self.answers = answers
        self.healthy = healthy
        self.raise_for = set(raise_for)

    def _lookup(self, title_id):
        if title_id in self.raise_for:
            raise RuntimeError("arr is down")
        value = self.answers.get(title_id, 404)
        if isinstance(value, str):
            return 200, {"path": value}
        return value, None

    def _by_id(self, title_id):
        status, body = self._lookup(title_id)
        return body if status == 200 else None

    def health_check(self):
        return (self.healthy, "OK" if self.healthy else "down")


class _Sonarr(_Arr):
    def get_series_by_id(self, series_id):
        return self._by_id(series_id)

    def lookup_series(self, series_id):
        return self._lookup(series_id)


class _Radarr(_Arr):
    def get_movie_by_id(self, movie_id):
        return self._by_id(movie_id) or {}

    def lookup_movie(self, movie_id):
        return self._lookup(movie_id)


# --- I5 -----------------------------------------------------------------------


def test_resolve_policy_returns_none_on_a_resolution_error(app_ctx, monkeypatch):
    import services.inheritance_resolver as inheritance_resolver
    from services.foreign_tracks.policy import resolve_policy

    _add_series(11, cleanup_keep_sdh=True)
    monkeypatch.setattr(inheritance_resolver, "resolve_for_series", _boom)
    assert resolve_policy(series_id=11) is None


def test_resolve_policy_without_an_override_row_is_the_global_policy(app_ctx):
    from config import get_settings
    from services.foreign_tracks.policy import policy_from_settings, resolve_policy

    assert resolve_policy(series_id=12345) == policy_from_settings(get_settings())


def test_the_cleanup_hook_fails_and_never_strips_when_the_policy_is_unresolvable(
    app_ctx, monkeypatch
):
    from config import get_settings
    from services import foreign_track_cleanup as ftc

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", True)
    with (
        patch("services.foreign_tracks.policy.resolve_policy", return_value=None),
        patch("remux.remove_foreign_subtitle_streams", return_value="/bak") as strip,
    ):
        outcome = ftc.maybe_run_foreign_track_cleanup(
            {"sonarr_series_id": 5, "target_language": "de"}, "/m/x.mkv", {"de"}
        )
    assert outcome == ftc.CLEANUP_FAILED
    assert not strip.called


def test_an_unresolvable_policy_makes_the_override_set_incomplete(app_ctx, monkeypatch):
    import sonarr_client
    from services.foreign_tracks import policy as pol

    _add_series(21, cleanup_keep_sdh=True)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({21: "/media/A"})
    )
    monkeypatch.setattr(pol, "resolve_policy", lambda **kw: None)
    result = pol.override_paths()
    assert result.complete is False
    assert result.pairs == []
    assert "series 21" in result.failed


# --- I4 -----------------------------------------------------------------------


def test_a_series_sonarr_confirms_missing_is_skipped_and_stays_complete(app_ctx, monkeypatch):
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(31, cleanup_keep_sdh=True)
    _add_series(32, cleanup_keep_sdh=True)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({32: "/media/B"})
    )
    result = override_paths()
    assert result.complete is True
    assert [p.replace("\\", "/") for p, _ in result.pairs] == ["/media/B"]
    assert result.failed == ()


def test_a_movie_radarr_confirms_missing_is_skipped_and_stays_complete(app_ctx, monkeypatch):
    import radarr_client
    from services.foreign_tracks.policy import override_paths

    _add_movie(41, cleanup_keep_sdh=True)
    monkeypatch.setattr(radarr_client, "get_radarr_client", lambda *a, **k: _Radarr({}))
    result = override_paths()
    assert result.complete is True
    assert result.pairs == []


def test_a_none_from_an_unreachable_sonarr_is_not_confirmed_missing(app_ctx, monkeypatch):
    """The arr clients swallow connection errors and return None — a None is
    only "missing" when the arr itself answers its health check."""
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(51, cleanup_keep_sdh=True)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({51: None}, healthy=False)
    )
    result = override_paths()
    assert result.complete is False
    assert "series 51" in result.failed


def test_an_http_error_is_not_confirmed_missing_even_when_the_arr_is_healthy(app_ctx, monkeypatch):
    """A 500 (or 401, 503 ...) is an arr problem, not an answer about the
    title. The clients turn it into None and the health check still passes —
    only a real 404 may confirm "missing" (final review I4, RC blocker)."""
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(52, cleanup_keep_sdh=True)
    monkeypatch.setattr(sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({52: 500}))
    result = override_paths()
    assert result.complete is False
    assert result.failed == ("series 52",)


def test_a_timeout_on_a_healthy_radarr_is_not_confirmed_missing(app_ctx, monkeypatch):
    import radarr_client
    from services.foreign_tracks.policy import override_paths

    _add_movie(53, cleanup_foreign_tracks=False)
    monkeypatch.setattr(radarr_client, "get_radarr_client", lambda *a, **k: _Radarr({53: None}))
    result = override_paths()
    assert result.complete is False, "an excluded title must not silently lose its exclusion"
    assert result.excluded == []


def test_a_404_while_the_arr_fails_its_health_check_is_not_missing(app_ctx, monkeypatch):
    """A reverse proxy in front of a stopped Sonarr answers 404 to every path
    (Traefik, the Saturday 04:00 auto-update window). The health check then
    fails too — so every override must be kept, not dropped."""
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(54, cleanup_keep_sdh=True)
    _add_series(55, cleanup_foreign_tracks=False)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({}, healthy=False)
    )
    result = override_paths()
    assert result.complete is False
    assert set(result.failed) == {"series 54", "series 55"}


def test_only_the_default_instance_is_asked(app_ctx, monkeypatch):
    """Settings are keyed by the default instance's ids; a second instance may
    hold an unrelated title under the same id and must never be asked."""
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(56, cleanup_keep_sdh=True)
    asked = []

    def fake_get_sonarr_client(instance_name=None):
        asked.append(instance_name)
        return _Sonarr({56: "/media/Default/S56"})

    monkeypatch.setattr(sonarr_client, "get_sonarr_client", fake_get_sonarr_client)
    result = override_paths()
    assert asked == [None]
    assert [p.replace("\\", "/") for p, _ in result.pairs] == ["/media/Default/S56"]


def test_a_dead_arr_is_asked_once_per_run(app_ctx, monkeypatch):
    """No answer once → the remaining titles fail fast instead of each waiting
    for its own timeout."""
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    for series_id in (57, 58, 59):
        _add_series(series_id, cleanup_keep_sdh=True)
    arr = _Sonarr({57: None, 58: None, 59: None})
    calls = []
    original = arr.lookup_series
    arr.lookup_series = lambda sid: calls.append(sid) or original(sid)
    monkeypatch.setattr(sonarr_client, "get_sonarr_client", lambda *a, **k: arr)
    result = override_paths()
    assert len(calls) == 1
    assert set(result.failed) == {"series 57", "series 58", "series 59"}


def test_a_200_without_a_path_is_not_missing(app_ctx, monkeypatch):
    import radarr_client
    from services.foreign_tracks.policy import override_paths

    _add_movie(60, cleanup_keep_sdh=True)

    class _Odd(_Radarr):
        def lookup_movie(self, movie_id):
            return 200, {"title": "no path"}

    monkeypatch.setattr(radarr_client, "get_radarr_client", lambda *a, **k: _Odd({}))
    result = override_paths()
    assert result.complete is False


def test_a_raising_lookup_is_incomplete_and_named(app_ctx, monkeypatch):
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(61, cleanup_keep_sdh=True)
    _add_series(62, cleanup_keep_sdh=True)
    monkeypatch.setattr(
        sonarr_client,
        "get_sonarr_client",
        lambda *a, **k: _Sonarr({62: "/media/S62"}, raise_for={61}),
    )
    result = override_paths()
    assert result.complete is False
    assert result.failed == ("series 61",)
    assert len(result.pairs) == 1


# --- I7 -----------------------------------------------------------------------


def test_a_series_with_cleanup_off_is_an_excluded_folder(app_ctx, monkeypatch):
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(71, cleanup_foreign_tracks=False)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({71: "/media/Off"})
    )
    result = override_paths()
    assert [p.replace("\\", "/") for p in result.excluded] == ["/media/Off"]
    assert result.pairs == []
    assert result.complete is True


def test_a_movie_with_cleanup_off_is_an_excluded_folder(app_ctx, monkeypatch):
    import radarr_client
    from services.foreign_tracks.policy import override_paths

    _add_movie(81, cleanup_foreign_tracks=False, cleanup_keep_sdh=True)
    monkeypatch.setattr(
        radarr_client, "get_radarr_client", lambda *a, **k: _Radarr({81: "/media/M81"})
    )
    result = override_paths()
    assert [p.replace("\\", "/") for p in result.excluded] == ["/media/M81"]
    assert result.pairs == [], "an excluded title is never stripped, whatever its overrides"


def test_a_series_with_cleanup_on_is_not_excluded(app_ctx, monkeypatch):
    import sonarr_client
    from services.foreign_tracks.policy import override_paths

    _add_series(91, cleanup_foreign_tracks=True)
    monkeypatch.setattr(
        sonarr_client, "get_sonarr_client", lambda *a, **k: _Sonarr({91: "/media/On"})
    )
    result = override_paths()
    assert result.excluded == []


def test_is_excluded_matches_folders_not_text_prefixes():
    from services.foreign_tracks.policy import is_excluded

    assert is_excluded("/media/Anime/Show/e1.mkv", ["/media/Anime/Show"])
    assert not is_excluded("/media/Anime/Show Two/e1.mkv", ["/media/Anime/Show"])
    assert not is_excluded("/media/x.mkv", [])


def test_override_set_policy_type_is_unchanged():
    from services.foreign_tracks.policy import OverrideSet

    s = OverrideSet(pairs=[("/a", TrackPolicy())], excluded=[], complete=True, failed=())
    assert s.pairs[0][1] == TrackPolicy()


def test_the_preview_answers_503_when_the_policy_is_unresolvable(client, tmp_path, monkeypatch):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    with (
        patch("remux.get_media_streams", return_value={"streams": []}),
        patch("services.foreign_tracks.policy.resolve_policy", return_value=None),
    ):
        resp = client.post(
            "/api/v1/foreign-tracks/preview-file", json={"path": str(video), "series_id": 5}
        )
    assert resp.status_code == 503
    assert "policy" in resp.get_json()["error"].lower()
