"""Shared secret redaction — value pass, regex layer, and the logging filter.

The support-bundle scrubber used to be a regex deny-list with a 16-character
minimum on ``[A-Za-z0-9+/=_-]``. Everything below passed through it unchanged:
short passwords, DSN passwords, bearer tokens, Discord webhook tokens and keys
containing dots or punctuation. Each test names one such shape.
"""

from __future__ import annotations

import io
import json
import logging
import time

import pytest

from config_settings import Settings
from secret_redaction import (
    REDACTED,
    SecretRedactionFilter,
    collect_secret_values,
    redact,
)


class TestRegexLayer:
    """No settings involved — the second layer must stand on its own."""

    @pytest.mark.parametrize(
        ("line", "secret"),
        [
            ("login failed password=hunter2pass", "hunter2pass"),
            ("login failed password=abc", "abc"),
            ("passwd: s3cr", "s3cr"),
            ("pwd=x9", "x9"),
            ("connect postgresql://sublarr:S3cretPw@host:5432/db", "S3cretPw"),
            ("redis://:r3dis@cache:6379/0 refused", "r3dis"),
            ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOjF9.sig", "eyJhbGciOiJIUzI1NiJ9"),
            (
                "POST https://discord.com/api/webhooks/123456789012/AbCdEf-gh_ijKLmn failed",
                "AbCdEf-gh_ijKLmn",
            ),
            (
                "tgram bot123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                "AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            ),
            ("api_key=abc.def.ghi rejected", "abc.def.ghi"),
            ("token: 'abc$%^&*()xyz'", "abc$%^&*()xyz"),
            ('{"secret": "two words"}', "two words"),
            ("GET /api?apikey=short&x=1", "short"),
            ("X-Api-Key: k3y", "k3y"),
        ],
    )
    def test_secret_shape_is_redacted(self, line, secret):
        out = redact(line, values=())
        assert secret not in out, out
        assert REDACTED in out

    @pytest.mark.parametrize(
        "line",
        [
            "Found 12 tokens in batch",
            "max_tokens: 4096",
            "api_key=None",
            "Connected to http://sonarr:8989/api/v3",
            "Scanning /media/Anime/Show S01E01.mkv",
            "Basic auth failed",
        ],
    )
    def test_ordinary_lines_are_untouched(self, line):
        assert redact(line, values=()) == line

    def test_quotes_are_preserved(self):
        assert redact("token: 'abc'", values=()) == f"token: '{REDACTED}'"
        assert redact('"api_key": "abc"', values=()) == f'"api_key": "{REDACTED}"'

    def test_redaction_is_idempotent(self):
        once = redact("password=hunter2 postgresql://u:p4ss@h/db", values=())
        assert redact(once, values=()) == once

    def test_non_string_input_is_returned_unchanged(self):
        assert redact("", values=()) == ""
        assert redact(None, values=()) is None  # type: ignore[arg-type]


class TestValuePass:
    def test_exact_value_is_replaced_even_without_a_key_name(self):
        out = redact("upstream said: Zq9Short rejected", values=("Zq9Short",))
        assert "Zq9Short" not in out

    def test_longest_value_wins(self):
        out = redact("abcdEFGH1234", values=("abcd", "abcdEFGH1234"))
        assert out == REDACTED


class TestCollectSecretValues:
    def _settings(self, **kw):
        return Settings(**kw)

    def test_sensitive_fields_are_collected(self):
        s = self._settings(
            api_key="MainApiKey123", opensubtitles_password="osPw12", tvdb_pin="4711"
        )
        values = collect_secret_values(s)
        assert {"MainApiKey123", "osPw12"} <= values
        # Too short for the value pass (it would blank "4711" everywhere); the
        # regex layer still catches it next to its key name.
        assert "4711" not in values

    def test_defaults_of_sensitive_names_are_not_collected(self):
        # customapi_api_key_header defaults to "X-API-Key" — a public header name.
        values = collect_secret_values(self._settings())
        assert "X-API-Key" not in values

    def test_dsn_password_is_collected(self):
        s = self._settings(
            database_url="postgresql://sublarr:S3cretPw@db:5432/sublarr",
            redis_url="redis://default:r3disPass@cache:6379/0",
        )
        values = collect_secret_values(s)
        assert "S3cretPw" in values
        assert "r3disPass" in values

    def test_userinfo_password_in_any_url_field_is_collected(self):
        s = self._settings(ollama_url="http://me:0llamaPw@gpu:11434")
        assert "0llamaPw" in collect_secret_values(s)

    def test_nested_instance_api_keys_are_collected(self):
        s = self._settings(
            sonarr_instances_json=json.dumps(
                [{"name": "Main", "url": "http://sonarr:8989", "api_key": "NestedSonarrKey"}]
            ),
            radarr_instances_json=json.dumps([{"name": "4k", "apiKey": "NestedRadarrKey"}]),
            media_servers_json=json.dumps([{"type": "plex", "token": "PlexTok99"}]),
        )
        values = collect_secret_values(s)
        assert {"NestedSonarrKey", "NestedRadarrKey", "PlexTok99"} <= values

    def test_notification_url_tokens_are_collected(self):
        s = self._settings(
            notification_urls_json=json.dumps(
                ["discord://123456789012/AbCdEfWebhookTok", "tgram://123456:BotTokenValue/42"]
            )
        )
        values = collect_secret_values(s)
        assert "AbCdEfWebhookTok" in values
        assert any("BotTokenValue" in v for v in values)

    def test_malformed_json_does_not_raise(self):
        s = self._settings(sonarr_instances_json="{not json", api_key="StillHere1")
        assert "StillHere1" in collect_secret_values(s)

    def test_very_short_values_are_skipped(self):
        # A 1-3 character value would shred every log line it appears in.
        values = collect_secret_values(self._settings(tvdb_pin="12"))
        assert "12" not in values


class TestLiveValueSet:
    """redact() without explicit values reads the active settings singleton."""

    def test_follows_a_settings_reload(self, monkeypatch):
        import config_singleton

        monkeypatch.setattr(config_singleton, "_settings", Settings(jimaku_api_key="FirstKey1"))
        assert "FirstKey1" not in redact("x FirstKey1 y")

        monkeypatch.setattr(config_singleton, "_settings", Settings(jimaku_api_key="SecondKey2"))
        out = redact("x FirstKey1 SecondKey2 y")
        assert "SecondKey2" not in out
        # The old value is no longer a configured secret.
        assert "FirstKey1" in out

    def test_no_settings_yet_means_regex_only(self, monkeypatch):
        import config_singleton

        monkeypatch.setattr(config_singleton, "_settings", None)
        assert redact("password=x1") == f"password={REDACTED}"


def _logger_with_filter():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.addFilter(SecretRedactionFilter())
    log = logging.getLogger("test_secret_redaction.isolated")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.DEBUG)
    return log, stream


class TestFilter:
    def test_message_with_args_is_redacted(self):
        log, stream = _logger_with_filter()
        log.info("connecting to %s", "postgresql://u:TopSecret9@h/db")
        assert "TopSecret9" not in stream.getvalue()

    def test_exception_text_is_redacted(self):
        log, stream = _logger_with_filter()
        try:
            raise RuntimeError("auth failed password=Tr4ceback")
        except RuntimeError:
            log.exception("boom")
        out = stream.getvalue()
        assert "Tr4ceback" not in out
        assert "RuntimeError" in out  # the traceback itself survives

    def test_a_broken_redactor_never_drops_the_record(self, monkeypatch, capsys):
        import secret_redaction

        def _explode(*_a, **_k):
            raise ValueError("kaputt")

        monkeypatch.setattr(secret_redaction, "redact", _explode)
        monkeypatch.setattr(secret_redaction, "_warned", False)
        log, stream = _logger_with_filter()
        log.warning("still here")
        log.warning("and again")
        assert "still here" in stream.getvalue()
        assert "and again" in stream.getvalue()
        # One warning on stderr, not one per record.
        assert capsys.readouterr().err.count("secret redaction") == 1

    def test_a_record_with_bad_args_is_passed_on(self):
        f = SecretRedactionFilter()
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "%d", ("nope",), None)
        assert f.filter(record) is True

    def test_ten_thousand_records_are_cheap(self, monkeypatch):
        import config_singleton

        monkeypatch.setattr(
            config_singleton,
            "_settings",
            Settings(api_key="MainApiKey123", jimaku_api_key="JimakuKey99"),
        )
        f = SecretRedactionFilter()
        records = [
            logging.LogRecord(
                "wanted_search.process",
                logging.INFO,
                __file__,
                1,
                "Searching %s for episode %d of /media/Anime/Show/S01E%02d.mkv",
                ("jimaku", i, i % 24),
                None,
            )
            for i in range(10_000)
        ]
        start = time.perf_counter()
        for r in records:
            f.filter(r)
        elapsed = time.perf_counter() - start
        # ~20 µs per record on a dev box; the bound leaves room for slow CI.
        assert elapsed < 1.5, f"10k records took {elapsed:.3f}s"


def test_a_short_configured_value_does_not_blank_ordinary_words():
    """A weak password such as "anime" must not shred every log line of an
    anime library; next to its key name the regex layer still catches it."""
    from config_settings import Settings

    values = collect_secret_values(Settings(opensubtitles_password="anime"))
    assert "anime" not in values
    line = "Wanted 12: searching anime episode"
    assert redact(line, values) == line
    assert "anime" not in redact("login password=anime", values)


def test_a_short_pin_is_caught_next_to_its_key():
    assert "4711" not in redact("tvdb login pin=4711 ok", ())


def test_a_record_logged_while_collecting_values_does_not_deadlock(monkeypatch):
    """Value collection runs inside a logging filter; anything it logs (an
    import, a settings warning) re-enters redact() on the same thread. A plain
    Lock deadlocked there."""
    import threading

    import config_singleton
    import secret_redaction

    real_collect = secret_redaction.collect_secret_values

    def _collect_and_log(settings):
        secret_redaction.redact("nested record while collecting")
        return real_collect(settings)

    monkeypatch.setattr(secret_redaction, "collect_secret_values", _collect_and_log)
    monkeypatch.setattr(config_singleton, "_settings", Settings(jimaku_api_key="Reentrant9"))
    monkeypatch.setattr(secret_redaction, "_cached_settings", None)

    done = []
    worker = threading.Thread(target=lambda: done.append(redact("x Reentrant9")), daemon=True)
    worker.start()
    worker.join(timeout=5)

    assert done, "redact() deadlocked on re-entry"
    assert "Reentrant9" not in done[0]


@pytest.mark.parametrize(
    ("line", "leak"),
    [
        ("password=abc,def rejected", ",def"),
        ("token=abc)def", ")def"),
        ("secret: a}b]c", "b]c"),
    ],
)
def test_a_bare_value_runs_to_whitespace_not_to_punctuation(line, leak):
    """Review: the bare value stopped at `,`, so `password=abc,def` left `,def`."""
    out = redact(line, values=())
    assert leak not in out, out
