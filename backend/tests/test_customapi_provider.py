"""Unit tests for the generic Custom HTTP/JSON provider (customapi)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat, VideoQuery
from providers.customapi import (
    CustomApiProvider,
    _dot_get,
    _slugify,
    sync_instances,
)


def _make_provider(**config) -> CustomApiProvider:
    """Provider with a mocked HTTP session, initialized via real initialize()."""
    p = CustomApiProvider(**config)
    with patch("providers.customapi.create_session") as mock_cs:
        mock_cs.return_value = MagicMock()
        p.initialize()
    return p


def _response(status_code=200, payload=None, headers=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.headers = headers or {}
    resp.text = text
    return resp


class TestDotGet:
    def test_empty_path_returns_object(self):
        assert _dot_get([1, 2], "") == [1, 2]

    def test_nested_dict(self):
        assert _dot_get({"data": {"results": [1]}}, "data.results") == [1]

    def test_list_index(self):
        assert _dot_get({"pages": [{"items": ["x"]}]}, "pages.0.items") == ["x"]

    def test_missing_segment_returns_none(self):
        assert _dot_get({"a": {}}, "a.b.c") is None
        assert _dot_get([1], "5") is None


class TestInitialize:
    def test_import_and_name(self):
        p = CustomApiProvider()
        assert p.name == "customapi"

    def test_no_base_url_leaves_session_none(self):
        p = CustomApiProvider()
        p.initialize()
        assert p.session is None

    def test_invalid_base_url_rejected(self):
        p = CustomApiProvider(base_url="file:///etc/passwd")
        p.initialize()
        assert p.session is None

    def test_base_url_trailing_slash_stripped(self):
        p = _make_provider(base_url="http://192.168.1.10:8080/")
        assert p._base == "http://192.168.1.10:8080"
        assert p.session is not None

    def test_api_key_header_default(self):
        p = _make_provider(base_url="http://192.168.1.10", api_key="secret")
        p.session.headers.__setitem__.assert_any_call("X-API-Key", "secret")

    def test_authorization_header_gets_bearer_prefix(self):
        p = _make_provider(
            base_url="http://192.168.1.10", api_key="tok123", api_key_header="Authorization"
        )
        p.session.headers.__setitem__.assert_any_call("Authorization", "Bearer tok123")

    def test_authorization_header_with_scheme_kept_verbatim(self):
        p = _make_provider(
            base_url="http://192.168.1.10",
            api_key="Basic abc==",
            api_key_header="Authorization",
        )
        p.session.headers.__setitem__.assert_any_call("Authorization", "Basic abc==")

    def test_invalid_field_map_json_falls_back_to_defaults(self):
        p = _make_provider(base_url="http://192.168.1.10", field_map="{not json")
        assert p._field_map["subtitle_id"] == "id"

    def test_terminate_closes_session(self):
        p = _make_provider(base_url="http://192.168.1.10")
        session = p.session
        p.terminate()
        session.close.assert_called_once()
        assert p.session is None


class TestSearch:
    def _query(self, **kwargs):
        defaults = dict(
            series_title="Test Show", season=1, episode=2, languages=["de"], imdb_id="tt123"
        )
        defaults.update(kwargs)
        return VideoQuery(**defaults)

    def test_search_returns_empty_without_session(self):
        p = CustomApiProvider()
        assert p.search(self._query()) == []

    def test_default_contract_mapping(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(
            payload={
                "results": [
                    {
                        "id": "42",
                        "language": "de",
                        "download_url": "http://192.168.1.10/files/42.ass",
                        "filename": "ep2.ass",
                        "release": "Group-1080p",
                        "hearing_impaired": True,
                        "forced": False,
                        "matches": ["series", "season", "episode"],
                    }
                ]
            }
        )
        results = p.search(self._query())
        assert len(results) == 1
        r = results[0]
        assert r.provider_name == "customapi"
        assert r.subtitle_id == "42"
        assert r.language == "de"
        assert r.download_url == "http://192.168.1.10/files/42.ass"
        assert r.format == SubtitleFormat.ASS
        assert r.release_info == "Group-1080p"
        assert r.hearing_impaired is True
        assert r.matches == {"series", "season", "episode"}

    def test_search_params_include_query_metadata(self):
        p = _make_provider(base_url="http://192.168.1.10", extra_params=json.dumps({"apikey": "x"}))
        p.session.get.return_value = _response(payload={"results": []})
        p.search(self._query())
        args, kwargs = p.session.get.call_args
        assert args[0] == "http://192.168.1.10/search"
        params = kwargs["params"]
        assert params["series_title"] == "Test Show"
        assert params["season"] == 1
        assert params["episode"] == 2
        assert params["languages"] == "de"
        assert params["imdb_id"] == "tt123"
        assert params["apikey"] == "x"

    def test_relative_download_url_resolved(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(
            payload={"results": [{"id": "1", "language": "de", "download_url": "files/1.srt"}]}
        )
        results = p.search(self._query())
        assert results[0].download_url == "http://192.168.1.10/files/1.srt"

    def test_missing_download_url_uses_download_path(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(
            payload={"results": [{"id": "a/b", "language": "de"}]}
        )
        results = p.search(self._query())
        assert results[0].download_url == "http://192.168.1.10/download/a%2Fb"

    def test_language_defaults_to_single_query_language(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(payload={"results": [{"id": "1"}]})
        results = p.search(self._query())
        assert results[0].language == "de"

    def test_mismatched_language_skipped(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(payload={"results": [{"id": "1", "language": "fr"}]})
        assert p.search(self._query()) == []

    def test_top_level_array_response(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(payload=[{"id": "1", "language": "de"}])
        assert len(p.search(self._query())) == 1

    def test_results_path_and_field_map_override(self):
        p = _make_provider(
            base_url="http://192.168.1.10",
            results_path="data.subtitles",
            field_map=json.dumps(
                {"subtitle_id": "attributes.sid", "download_url": "attributes.file.url"}
            ),
        )
        p.session.get.return_value = _response(
            payload={
                "data": {
                    "subtitles": [
                        {
                            "attributes": {
                                "sid": 7,
                                "file": {"url": "http://192.168.1.10/d/7"},
                            },
                            "language": "de",
                        }
                    ]
                }
            }
        )
        results = p.search(self._query())
        assert results[0].subtitle_id == "7"
        assert results[0].download_url == "http://192.168.1.10/d/7"

    def test_items_without_id_skipped(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(
            payload={"results": [{"language": "de"}, "not-a-dict"]}
        )
        assert p.search(self._query()) == []

    def test_auth_error_raised(self):
        from providers.base import ProviderAuthError

        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(status_code=401)
        with pytest.raises(ProviderAuthError):
            p.search(self._query())

    def test_rate_limit_raised_with_retry_after(self):
        from providers.base import ProviderRateLimitError

        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(status_code=429, headers={"Retry-After": "120"})
        with pytest.raises(ProviderRateLimitError) as exc_info:
            p.search(self._query())
        assert exc_info.value.retry_after == 120

    def test_server_error_returns_empty(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(status_code=500, text="boom")
        assert p.search(self._query()) == []

    def test_network_error_returns_empty(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.side_effect = ConnectionError("refused")
        assert p.search(self._query()) == []


class TestDownload:
    def test_download_raises_without_session(self):
        from providers.base import ProviderError, SubtitleResult

        p = CustomApiProvider()
        r = SubtitleResult(provider_name="customapi", subtitle_id="1", language="de")
        with pytest.raises(ProviderError):
            p.download(r)

    def test_download_rejects_bad_scheme(self):
        from providers.base import ProviderError, SubtitleResult

        p = _make_provider(base_url="http://192.168.1.10")
        r = SubtitleResult(
            provider_name="customapi",
            subtitle_id="1",
            language="de",
            download_url="ftp://192.168.1.10/1.srt",
        )
        with pytest.raises(ProviderError, match="rejected"):
            p.download(r)

    def test_download_raw_subtitle(self):
        from providers.base import SubtitleResult

        p = _make_provider(base_url="http://192.168.1.10")
        r = SubtitleResult(
            provider_name="customapi",
            subtitle_id="1",
            language="de",
            filename="x.srt",
            download_url="http://192.168.1.10/d/1",
        )
        with patch("providers.customapi._stream_download", return_value=b"1\n00:00 sub"):
            content = p.download(r)
        assert content == b"1\n00:00 sub"
        assert r.format == SubtitleFormat.SRT

    def test_download_zip_prefers_ass(self):
        import io
        import zipfile

        from providers.base import SubtitleResult

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("sub.srt", "srt content")
            zf.writestr("sub.ass", "ass content")

        p = _make_provider(base_url="http://192.168.1.10")
        r = SubtitleResult(
            provider_name="customapi",
            subtitle_id="1",
            language="de",
            download_url="http://192.168.1.10/d/1",
        )
        with patch("providers.customapi._stream_download", return_value=buf.getvalue()):
            content = p.download(r)
        assert content == b"ass content"
        assert r.format == SubtitleFormat.ASS

    def test_result_for_download_builds_url(self):
        p = _make_provider(base_url="http://192.168.1.10")
        r = p.result_for_download("99", language="de")
        assert r.download_url == "http://192.168.1.10/download/99"


class TestHealthCheck:
    def test_unconfigured(self):
        p = CustomApiProvider()
        healthy, msg = p.health_check()
        assert not healthy

    def test_health_endpoint_ok(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(status_code=200, payload={"ok": True})
        healthy, msg = p.health_check()
        assert healthy

    def test_missing_health_endpoint_falls_back_to_base(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.side_effect = [_response(status_code=404), _response(status_code=200)]
        healthy, msg = p.health_check()
        assert healthy

    def test_auth_failure(self):
        p = _make_provider(base_url="http://192.168.1.10")
        p.session.get.return_value = _response(status_code=401)
        healthy, msg = p.health_check()
        assert not healthy
        assert "Authentication" in msg


class TestInstances:
    def test_slugify(self):
        assert _slugify("My Server #1") == "my-server-1"
        assert _slugify("---") == ""

    def _sync_with(self, raw_json: str):
        settings = MagicMock()
        settings.customapi_instances_json = raw_json
        with patch("config.get_settings", return_value=settings):
            sync_instances()

    def test_sync_registers_and_removes_instances(self):
        from providers.registry import _PROVIDER_CLASSES

        try:
            self._sync_with(
                json.dumps(
                    [
                        {"name": "Home NAS", "base_url": "http://192.168.1.10:9000"},
                        {"name": "no-url"},
                    ]
                )
            )
            assert "customapi-home-nas" in _PROVIDER_CLASSES
            cls = _PROVIDER_CLASSES["customapi-home-nas"]
            assert cls.name == "customapi-home-nas"
            assert cls.config_fields == []

            # Instance config drives initialize()
            p = cls()
            with patch("providers.customapi.create_session") as mock_cs:
                mock_cs.return_value = MagicMock()
                p.initialize()
            assert p._base == "http://192.168.1.10:9000"

            # Removing the instance from config drops the registration
            self._sync_with("[]")
            assert "customapi-home-nas" not in _PROVIDER_CLASSES
        finally:
            for name in [n for n in _PROVIDER_CLASSES if n.startswith("customapi-")]:
                del _PROVIDER_CLASSES[name]

    def test_sync_with_invalid_json_is_noop(self):
        from providers.registry import _PROVIDER_CLASSES

        before = set(_PROVIDER_CLASSES)
        self._sync_with("{broken")
        assert set(_PROVIDER_CLASSES) == before


class TestDownloadUrlValidation:
    def test_customapi_allows_arbitrary_private_host(self):
        from security_utils import validate_download_url

        ok, err = validate_download_url("http://192.168.1.10:9000/d/1", "customapi")
        assert ok, err

    def test_instance_names_allowed(self):
        from security_utils import validate_download_url

        ok, err = validate_download_url("http://10.0.0.5/d/1", "customapi-home-nas")
        assert ok, err

    def test_metadata_ip_blocked(self):
        from security_utils import validate_download_url

        ok, err = validate_download_url("http://169.254.169.254/latest", "customapi")
        assert not ok
