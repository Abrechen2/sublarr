"""Catalog providers (providers/hub): adapter, loader and settings plumbing.

A tiny bundle written by this test stands in for the catalog — it speaks the
same contract (``search(video, languages, config)`` returning candidate dicts,
``download(payload, language, config)`` returning ``content_b64`` or
``archive_b64``) without touching the network or the vendored code.
"""

import base64
import hashlib
import io
import json
import urllib.error
import zipfile
from unittest.mock import patch

import pytest

from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    SubtitleFormat,
    VideoQuery,
)
from providers.hub import (
    BUNDLES_DIR,
    build_provider_class,
    config_fields_for,
    discover_bundles,
    secret_config_keys,
    verify_bundle,
)
from providers.hub.adapter import scored_matches, translate_error, video_from_query

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"

_BUNDLE_CODE = """
import base64, hashlib, io, zipfile

LAST = {}


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class FakeProvider:
    def search(self, video, languages, config):
        LAST["video"], LAST["languages"], LAST["config"] = video, languages, config
        lang = languages[0]
        return [
            {
                "provider": "fakehub",
                "id": "one",
                "language": {"alpha3": lang["alpha3"], "hi": False, "forced": False},
                "release_info": "Show.S01E02.1080p.WEB",
                "filename": "show.s01e02.srt",
                "matches": ["series_imdb_id", "season", "episode", "country", "fps"],
                "score": 999,
                "hearing_impaired": False,
                "ai_translated": True,
                "display": {"uploader": "someone"},
                "provider_payload": {"mode": config.get("mode", "plain")},
            },
            {"provider": "fakehub", "id": "broken"},
        ]

    def download(self, payload, language, config):
        body = b"1\\n00:00:01,000 --> 00:00:02,000\\nHallo\\n"
        mode = payload.get("mode")
        if mode == "plain":
            return {"content_b64": base64.b64encode(body).decode(), "content_sha256":
                    hashlib.sha256(body).hexdigest(), "format": "srt", "empty": False}
        if mode == "badsum":
            return {"content_b64": base64.b64encode(body).decode(), "content_sha256": "0" * 64,
                    "empty": False}
        if mode == "pack":
            data = _zip({"Show - S01E01.srt": b"wrong", "Show - S01E02.ass": b"[Script Info]",
                         "Show - S01E03.srt": b"wrong"})
            return {"archive_b64": base64.b64encode(data).decode()}
        if mode == "select":
            data = _zip({"简体 [en].srt": b"en", "节目 [de] 最终.srt": body})
            return {"archive_b64": base64.b64encode(data).decode(), "select_member": True}
        return None

    def select_archive_member(self, payload, language, members, config):
        if config.get("reject"):
            return {"decision": "reject"}
        return {"decision": "pin", "member": "节目 [de] 最终.srt"}
"""


def _manifest(files, **extra):
    manifest = {
        "provider_id": "fakehub",
        "name": "Fake Hub",
        "entry_module": "provider",
        "entry_class": "FakeProvider",
        "languages": ["deu", "eng", "por-BR", "zho-Hant"],
        "supported_media": ["episode"],
        "config_schema": {
            "type": "object",
            "required": ["token"],
            "properties": {
                "token": {"type": "string", "title": "API token", "secret": True},
                "mode": {
                    "type": "string",
                    "title": "Mode",
                    "enum": ["plain", "pack"],
                    "default": "plain",
                },
                "vip": {"type": "boolean", "title": "VIP", "default": False},
                "limit": {"type": "integer", "title": "Limit", "default": 5},
                "reject": {"type": "boolean", "title": "Reject", "default": False},
            },
        },
        "secret_fields": ["token"],
        "files": files,
    }
    manifest.update(extra)
    return manifest


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "bundles"
    bundle_dir = root / "fakehub"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "provider.py").write_text(_BUNDLE_CODE)
    digest = hashlib.sha256(_BUNDLE_CODE.encode()).hexdigest()
    manifest = _manifest({"provider.py": digest})
    (bundle_dir / "provider.json").write_text(json.dumps(manifest))
    return root, bundle_dir, manifest


def _provider(bundle, **config):
    _root, bundle_dir, manifest = bundle
    cls = build_provider_class("fakehub", str(bundle_dir), manifest)
    provider = cls(**{"token": "secret", **config})
    provider.initialize()
    return provider


def _episode_query(**overrides):
    base = dict(
        series_title="Show",
        season=1,
        episode=2,
        imdb_id="tt0000001",
        languages=["de"],
        file_path="/media/Show/S01/Show - S01E02.mkv",
        file_hash="abc123",
    )
    base.update(overrides)
    return VideoQuery(**base)


# -- loader --------------------------------------------------------------------


def test_an_edited_bundle_file_is_refused(bundle):
    _root, bundle_dir, manifest = bundle
    assert verify_bundle(str(bundle_dir), manifest) == []
    (bundle_dir / "provider.py").write_text(_BUNDLE_CODE + "\n# tampered\n")
    assert verify_bundle(str(bundle_dir), manifest) == ["provider.py"]


def test_manifest_settings_become_dotted_config_fields(bundle):
    _root, _dir, manifest = bundle
    fields = {f["key"]: f for f in config_fields_for("fakehub", manifest)}

    assert fields["hub.fakehub.token"]["type"] == "password"
    assert fields["hub.fakehub.token"]["required"] is True
    assert fields["hub.fakehub.mode"]["type"] == "select"
    assert fields["hub.fakehub.mode"]["options"] == ["plain", "pack"]
    assert fields["hub.fakehub.vip"]["type"] == "checkbox"
    assert fields["hub.fakehub.vip"]["default"] == "false"
    assert fields["hub.fakehub.limit"]["type"] == "number"


def test_secret_keys_come_from_the_manifests_alone(bundle):
    root, _dir, _manifest = bundle
    assert secret_config_keys(str(root)) == {"hub.fakehub.token"}


def test_the_generated_class_declares_sublarr_language_codes(bundle):
    _root, bundle_dir, manifest = bundle
    cls = build_provider_class("fakehub", str(bundle_dir), manifest)
    assert {"de", "en", "pt", "zh", "zh-hant"} <= cls.languages
    assert cls.opt_in is True


# -- lifecycle -----------------------------------------------------------------


def test_missing_required_credentials_leave_it_inactive(bundle):
    provider = _provider(bundle, token="")
    assert provider.session is None
    assert provider.search(_episode_query()) == []


def test_stored_strings_reach_the_bundle_as_schema_types(bundle):
    provider = _provider(bundle, vip="true", limit="7", mode="")
    provider.search(_episode_query())
    config = provider.impl_class.search.__globals__["LAST"]["config"]
    assert config == {"token": "secret", "mode": "plain", "vip": True, "limit": 7, "reject": False}


# -- search --------------------------------------------------------------------


def test_a_candidate_becomes_a_sublarr_result(bundle):
    provider = _provider(bundle)
    results = provider.search(_episode_query())

    assert len(results) == 1  # the candidate without provider_payload is dropped
    result = results[0]
    assert result.language == "de"
    assert result.format is SubtitleFormat.SRT
    assert result.matches == {"series", "year", "season", "episode"}
    assert result.score == 0  # the bundle's own score is not trusted
    assert result.machine_translated is True
    assert result.uploader_name == "someone"


def test_a_movie_search_skips_an_episode_only_bundle(bundle):
    provider = _provider(bundle)
    assert provider.search(VideoQuery(title="Film", year=2020, languages=["de"])) == []


def test_the_video_dict_carries_series_ids_not_episode_ids():
    video = video_from_query(_episode_query(tvdb_id=5, anidb_id=9, absolute_episode=14))
    assert video["kind"] == "episode"
    assert video["series"] == "Show"
    assert video["series_imdb_id"] == "tt0000001"
    assert "imdb_id" not in video
    assert video["hashes"] == {"opensubtitles": "abc123"}
    assert video["absolute_episode"] == 14


@pytest.mark.parametrize(
    ("raw", "kind", "expected"),
    [
        (["imdb_id"], "movie", {"title", "year"}),
        (["imdb_id"], "episode", {"series", "season", "episode"}),
        (["absolute_episode"], "episode", {"season", "episode"}),
        (["title", "season"], "movie", {"title"}),
        (["edition", "streaming_service", "fps"], "movie", set()),
    ],
)
def test_match_names_map_onto_what_sublarr_scores(raw, kind, expected):
    assert scored_matches(raw, kind) == expected


# -- download ------------------------------------------------------------------


def test_content_b64_is_decoded_and_checked(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    assert provider.download(result) == SRT
    assert result.content == SRT


def test_a_checksum_mismatch_is_an_error(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "badsum"}
    with pytest.raises(ProviderError, match="checksum"):
        provider.download(result)


def test_a_season_pack_yields_the_wanted_episode(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "pack"}

    assert provider.download(result) == b"[Script Info]"
    assert result.filename == "Show - S01E02.ass"
    assert result.format is SubtitleFormat.ASS


def test_a_pack_without_the_episode_is_not_a_download(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query(episode=9))[0]
    result.provider_data["payload"] = {"mode": "pack"}
    with pytest.raises(ProviderError, match="no file for this episode"):
        provider.download(result)


def test_the_bundle_pins_the_archive_member_in_the_wanted_language(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "select"}
    assert provider.download(result) == SRT


def test_a_rejected_archive_is_an_error(bundle):
    provider = _provider(bundle, reject="true")
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "select"}
    with pytest.raises(ProviderError, match="wanted language"):
        provider.download(result)


def test_no_content_is_an_error(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "nothing"}
    with pytest.raises(ProviderError):
        provider.download(result)


# -- errors --------------------------------------------------------------------


class RateLimited(RuntimeError):  # noqa: N818 — the name the bundles use
    pass


def _http_error(code, headers=None):
    return urllib.error.HTTPError("https://x", code, "x", headers or {}, io.BytesIO(b""))


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_http_error(429, {"Retry-After": "30"}), ProviderRateLimitError),
        (_http_error(403), ProviderAuthError),
        (_http_error(500), ProviderError),
        (RateLimited("slow down"), ProviderRateLimitError),
        (PermissionError("login failed"), ProviderAuthError),
        (TimeoutError("late"), ProviderTimeoutError),
        (ValueError("parse"), ProviderError),
    ],
)
def test_bundle_errors_map_onto_provider_errors(exc, expected):
    translated = translate_error(exc)
    assert type(translated) is expected
    if isinstance(translated, ProviderRateLimitError) and isinstance(exc, urllib.error.HTTPError):
        assert translated.retry_after == 30


# -- settings plumbing ---------------------------------------------------------


def test_hub_settings_are_read_from_config_entries(bundle):
    from providers.manager_config_mixin import _hub_provider_config

    _root, bundle_dir, manifest = bundle
    cls = build_provider_class("fakehub", str(bundle_dir), manifest)
    stored = {"hub.fakehub.token": "  tok  ", "hub.fakehub.vip": "true"}
    with patch("db.config.get_config_entry", side_effect=stored.get):
        config = _hub_provider_config(cls)

    assert config["token"] == "tok"
    assert config["vip"] == "true"
    assert config["mode"] == "plain"  # schema default for an unset field


def test_get_config_masks_hub_secrets(bundle):
    from routes.config.core import _hub_config_entries

    root, _dir, _manifest = bundle
    stored = {"hub.fakehub.token": "tok", "hub.fakehub.mode": "pack", "other": "x"}
    with (
        patch("db.config.get_all_config_entries", return_value=stored),
        patch("providers.hub.secret_config_keys", return_value={"hub.fakehub.token"}),
    ):
        out = _hub_config_entries()

    assert out == {"hub.fakehub.token": "***configured***", "hub.fakehub.mode": "pack"}


# -- the vendored catalog itself (read only — nothing here imports a bundle) ---


def test_every_vendored_bundle_matches_its_manifest():
    bundles = discover_bundles(BUNDLES_DIR)
    assert len(bundles) >= 40
    tampered = {hub_id: verify_bundle(path, manifest) for hub_id, path, manifest in bundles}
    assert {k: v for k, v in tampered.items() if v} == {}


def test_no_vendored_bundle_shadows_a_builtin_provider():
    from providers.registry import _BUILTIN_PROVIDERS

    assert not {hub_id for hub_id, _p, _m in discover_bundles(BUNDLES_DIR)} & set(
        _BUILTIN_PROVIDERS
    )


def test_a_manifest_that_does_not_hash_its_entry_module_is_refused(bundle):
    _root, bundle_dir, manifest = bundle
    assert verify_bundle(str(bundle_dir), {**manifest, "files": {}}) == ["provider.py"]


def test_archive_guard_errors_become_provider_errors(bundle):
    provider = _provider(bundle)
    result = provider.search(_episode_query())[0]
    result.provider_data["payload"] = {"mode": "pack"}
    with (
        patch("archive_utils.extract_subtitles_from_zip", side_effect=ValueError("ZIP bomb")),
        pytest.raises(ProviderError, match="refused"),
    ):
        provider.download(result)


def test_chinese_is_matched_by_country_as_the_bundles_send_it():
    from providers.hub.languages import manifest_languages, request_payloads, result_language

    assert request_payloads(["zh-hans"])[0]["country_alpha2"] == "CN"
    assert result_language({"alpha3": "zho", "country_alpha2": "CN"}, ["zh-hans"]) == "zh-hans"
    assert result_language({"alpha3": "zho", "country_alpha2": "TW"}, ["zh-hant"]) == "zh-hant"
    assert result_language({"alpha3": "zho"}, ["zh-hant"], hint="show.繁体.ass") == "zh-hant"
    assert manifest_languages(["zho"]) == {"zh", "zh-hans", "zh-hant"}


def test_catalog_credentials_are_secret_everywhere():
    from config_settings import is_sensitive_config_key
    from export_formats import _mask_config_secrets
    from sensitive_keys import is_sensitive_key

    assert is_sensitive_key("hub.titulky.password")  # encrypted at rest
    assert is_sensitive_config_key("hub.avistaz.cookies")  # masked in API/export
    assert not is_sensitive_config_key("hub.avistaz.user_agent")
    assert not is_sensitive_key("plugin.x.password")  # other namespaces unchanged
    masked = _mask_config_secrets({"hub.titulky.password": "hunter2-long"})
    assert masked["hub.titulky.password"] != "hunter2-long"


def test_an_empty_provider_list_does_not_enable_opt_in_providers(bundle):
    from providers.registry import _PROVIDER_CLASSES, resolve_enabled_names

    _root, bundle_dir, manifest = bundle
    cls = build_provider_class("fakehub", str(bundle_dir), manifest)
    with patch.dict(_PROVIDER_CLASSES, {"fakehub": cls}):
        assert "fakehub" not in resolve_enabled_names("")
        assert "fakehub" in resolve_enabled_names("opensubtitles,fakehub")


def test_switching_the_catalog_off_unregisters_its_providers(bundle):
    from providers.registry import _PROVIDER_CLASSES, _unregister_hub_providers

    _root, bundle_dir, manifest = bundle
    cls = build_provider_class("fakehub", str(bundle_dir), manifest)
    with patch.dict(_PROVIDER_CLASSES, {"fakehub": cls}):
        _unregister_hub_providers()
        assert "fakehub" not in _PROVIDER_CLASSES


def test_an_any_language_search_asks_a_small_bundle_for_all_it_serves(bundle):
    provider = _provider(bundle)
    provider.search(_episode_query(languages=[]))
    asked = provider.impl_class.search.__globals__["LAST"]["languages"]
    assert {lang["alpha3"] for lang in asked} >= {"deu", "eng", "por", "zho"}


def test_an_any_language_search_asks_a_large_bundle_for_the_installs_languages(bundle):
    from types import SimpleNamespace

    provider = _provider(bundle)
    provider.languages = {f"x{i}" for i in range(20)} | {"de", "en"}
    with patch(
        "config.get_settings",
        return_value=SimpleNamespace(target_language="de", source_language="en"),
    ):
        provider.search(_episode_query(languages=[]))
    asked = provider.impl_class.search.__globals__["LAST"]["languages"]
    assert [lang["alpha3"] for lang in asked] == ["deu", "eng"]
