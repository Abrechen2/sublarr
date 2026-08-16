"""Tests for app_logging._setup_logging third-party noise capping.

Regression guard for the 20s page-open report on low-power hosts
(Discord/Elric, DS920+, 1.9.4-rc.2): with log_level=DEBUG the root logger
level applied to EVERY library. rebulk (guessit's engine) emits ~155 DEBUG
records per filename parse; during a wanted-search burst that produced
~8k records/minute, each formatted twice (file + WebSocket handler),
written to disk, and emitted to connected browsers — saturating weak CPUs
and starving concurrent API requests.

User-selected DEBUG must apply to Sublarr's own loggers only; noisy
third-party libraries stay capped.
"""

import logging
import os
from types import SimpleNamespace

import pytest

from app_logging import (
    LOG_BACKUP_COUNT_DEFAULT,
    LOG_BACKUP_COUNT_MAX,
    SocketIOLogHandler,
    _setup_logging,
)


@pytest.fixture
def restore_root_logger(tmp_path):
    """Snapshot and restore root logger + third-party logger levels."""
    root = logging.getLogger()
    prev_level = root.level
    prev_handlers = list(root.handlers)
    third_party = ["rebulk", "guessit", "watchdog", "urllib3", "apscheduler"]
    prev_tp_levels = {name: logging.getLogger(name).level for name in third_party}
    yield
    for handler in list(root.handlers):
        if handler not in prev_handlers:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    root.setLevel(prev_level)
    for name, level in prev_tp_levels.items():
        logging.getLogger(name).setLevel(level)


def _settings(tmp_path, level="DEBUG"):
    return SimpleNamespace(
        log_level=level,
        log_file=str(tmp_path / "sublarr.log"),
        log_format="text",
    )


def test_debug_level_caps_noisy_third_party_loggers(restore_root_logger, tmp_path):
    """log_level=DEBUG must NOT turn on rebulk/guessit/watchdog/urllib3 debug spam."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    for name in ("rebulk", "guessit", "watchdog", "urllib3"):
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING, (
            f"{name} must stay capped at WARNING even when Sublarr runs at DEBUG"
        )


def test_debug_level_keeps_apscheduler_at_info(restore_root_logger, tmp_path):
    """APScheduler job-run INFO lines are useful — cap at INFO, not WARNING."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    assert logging.getLogger("apscheduler").getEffectiveLevel() == logging.INFO


def test_debug_level_still_applies_to_sublarr_loggers(restore_root_logger, tmp_path):
    """Sublarr's own loggers must still honour the user-selected DEBUG level."""
    _setup_logging(_settings(tmp_path, "DEBUG"))

    assert logging.getLogger().level == logging.DEBUG
    assert logging.getLogger("providers.search_coordinator").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("wanted_search.process").getEffectiveLevel() == logging.DEBUG


def test_websocket_handler_never_forwards_below_info(restore_root_logger, tmp_path):
    """The WebSocket log handler must not stream DEBUG records to browsers.

    Every record emitted to the root logger passes through SocketIOLogHandler
    and out to ALL connected clients. At DEBUG volume this floods both the
    server (per-record serialize + emit) and every open browser tab.
    """
    _setup_logging(_settings(tmp_path, "DEBUG"))

    ws_handlers = [h for h in logging.getLogger().handlers if isinstance(h, SocketIOLogHandler)]
    assert ws_handlers, "SocketIOLogHandler must be installed"
    assert all(h.level >= logging.INFO for h in ws_handlers)


class TestRequestIdInTextFormat:
    """A request's ordinary lines must be correlatable, not just its error line.

    request_id was assigned per request and stored on flask.g, but only
    interpolated by hand into error messages. The default text format — the one
    users actually send — carried it nowhere, so an error could be traced back
    to its request id while everything that request did before failing could
    not be found.

    The trap this guards: `%(request_id)s` raises while FORMATTING any record
    that lacks the attribute, which is every record from a thread, the
    scheduler, or a third-party library. A formatting error inside logging is
    especially bad — the record is lost and the traceback goes to stderr.
    """

    def _lines(self, tmp_path):
        return (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()

    def test_format_carries_the_request_id(self):
        from app_logging import LOG_FORMAT

        assert "%(request_id)s" in LOG_FORMAT

    def test_records_outside_a_request_get_a_placeholder(self, restore_root_logger, tmp_path):
        _setup_logging(_settings(tmp_path, "INFO"))
        logging.getLogger("services.scheduler.ticks").info("scheduler tick")

        line = [ln for ln in self._lines(tmp_path) if "scheduler tick" in ln][0]
        assert "[-]" in line

    def test_records_inside_a_request_carry_its_id(self, restore_root_logger, tmp_path):
        from flask import Flask, g

        _setup_logging(_settings(tmp_path, "INFO"))
        app = Flask(__name__)
        with app.test_request_context("/api/v1/wanted"):
            g.request_id = "abc123def456"
            logging.getLogger("routes.wanted").info("listing wanted")

        line = [ln for ln in self._lines(tmp_path) if "listing wanted" in ln][0]
        assert "abc123def456" in line

    def test_a_directly_constructed_record_still_formats(self, restore_root_logger, tmp_path):
        # Bypasses the LogRecord factory entirely, the way a library that builds
        # its own records does. Must not raise, and must not lose the record.
        _setup_logging(_settings(tmp_path, "INFO"))
        handler = _rotating_handler()
        record = logging.LogRecord(
            "third_party", logging.WARNING, __file__, 1, "raw record", None, None
        )
        handler.handle(record)

        assert any("raw record" in ln for ln in self._lines(tmp_path))

    def test_repeated_setup_does_not_nest_the_factory(self, restore_root_logger, tmp_path):
        # _setup_logging runs on every config save and on startup re-apply.
        # A factory wrapper installed each time would stack N deep.
        for _ in range(3):
            _setup_logging(_settings(tmp_path, "INFO"))
        logging.getLogger("probe").info("after three setups")

        line = [ln for ln in self._lines(tmp_path) if "after three setups" in ln][0]
        assert line.count("[-]") == 1

    def test_fingerprint_survives_the_new_format(self, restore_root_logger, tmp_path):
        # The interaction that would otherwise break silently: the fingerprint is
        # written by calling handler.format() directly, bypassing handler filters,
        # so it must still obtain a request_id from somewhere or vanish into the
        # swallow-all except in _write_fingerprint.
        _setup_logging(_settings(tmp_path, "INFO"))

        first = self._lines(tmp_path)[0]
        assert "sublarr-instance:" in first, "the fingerprint must survive the format change"


class TestRequestIdInJSONFormat:
    """The JSON format has to answer the same question the text format does.

    `StructuredJSONFormatter` looked the id up in `flask.g` itself instead of
    reading the one the record factory had already resolved. That made it a
    request-only field: scheduler runs, webhook follow-up and queue-drain work
    — most of what Sublarr does — shipped to ELK/Loki with no correlation id at
    all, while the text format showed one. Anyone on `log_format=json` would
    have lost the run label added in 1.12.1 without a single test noticing.
    """

    def _entry(self, record):
        import json

        from app_logging import StructuredJSONFormatter

        return json.loads(StructuredJSONFormatter().format(record))

    def _record(self, **attrs):
        record = logging.LogRecord(
            "wanted_search.process", logging.INFO, __file__, 1, "searching", None, None
        )
        for key, value in attrs.items():
            setattr(record, key, value)
        return record

    def test_carries_a_scheduler_run_label(self):
        entry = self._entry(self._record(request_id="wanted_search:a1b2c3d4"))

        assert entry["request_id"] == "wanted_search:a1b2c3d4"

    def test_carries_a_request_id(self):
        entry = self._entry(self._record(request_id="abc123def456"))

        assert entry["request_id"] == "abc123def456"

    def test_omits_the_placeholder_rather_than_shipping_it(self):
        from app_logging import NO_REQUEST_ID

        entry = self._entry(self._record(request_id=NO_REQUEST_ID))

        assert "request_id" not in entry

    def test_a_record_without_the_attribute_still_formats(self):
        # A library that builds its own records never goes through the factory.
        entry = self._entry(self._record())

        assert "request_id" not in entry
        assert entry["message"] == "searching"


class TestLogFingerprint:
    """The log file must identify the instance that produced it.

    Real cost of not doing this: two users attached `sublarr.log` to Discord
    bug reports and establishing which machine each came from took hours of
    forensics — one turned out not to be from the reporter's instance at all.
    A header written only at startup is not enough, because rotation pushes it
    out of the file the user actually uploads, so it is re-emitted into every
    new file on rollover.
    """

    def test_fresh_log_starts_with_a_fingerprint(self, restore_root_logger, tmp_path):
        _setup_logging(_settings(tmp_path))
        logging.getLogger("probe").info("first real line")

        first = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()[0]
        assert "sublarr-instance:" in first

    def test_fingerprint_reports_the_triage_facts(self, restore_root_logger, tmp_path):
        import config_singleton

        settings = _settings(tmp_path)
        settings.standalone_enabled = True
        settings.sonarr_url = ""
        settings.log_max_size_mb = 12
        settings.log_backup_count = 4
        # The payload is read from the live settings at write time, which in
        # production is always this singleton (create_app and the settings-save
        # path both hand _setup_logging the object they just installed).
        config_singleton._settings = settings
        _setup_logging(settings)

        first = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()[0]
        # The three questions actually asked in every Discord bug report.
        assert "version=" in first
        assert "os=" in first
        assert "mode=standalone" in first
        assert "rotation=12MBx4" in first

    def test_fingerprint_names_the_arr_mode_when_sonarr_is_configured(
        self, restore_root_logger, tmp_path
    ):
        import config_singleton

        settings = _settings(tmp_path)
        settings.standalone_enabled = False
        settings.sonarr_url = "http://sonarr:8989"
        config_singleton._settings = settings
        _setup_logging(settings)

        first = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()[0]
        assert "mode=arr" in first

    def test_rollover_writes_the_fingerprint_into_the_new_file(self, restore_root_logger, tmp_path):
        # The durability property: the file a user uploads after weeks of
        # uptime is a ROTATED one, which a startup-only header never reaches.
        settings = _settings(tmp_path, level="INFO")
        settings.log_max_size_mb = 1
        _setup_logging(settings)

        handler = _rotating_handler()
        handler.doRollover()
        logging.getLogger("probe").info("line after rollover")

        lines = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()
        assert "sublarr-instance:" in lines[0], (
            "a rotated-into file must re-state the fingerprint, or the log a user "
            "uploads carries no identity at all"
        )

    def test_existing_log_file_gets_stamped_on_startup(self, restore_root_logger, tmp_path):
        """The upgrade case — and the one that matters most.

        Found on a real RC deploy, not in tests: the first stamp was written only
        into an EMPTY file, so an instance upgrading with a populated
        /config/sublarr.log got no fingerprint at all until the file happened to
        rotate. That is precisely the user who upgrades and immediately attaches
        their log to a bug report. Every earlier test used a fresh tmp_path file,
        so none of them could see it.
        """
        import app_logging

        app_logging._stamped_log_paths.clear()
        log = tmp_path / "sublarr.log"
        log.write_text(
            "2026-07-31 01:51:46,996 [INFO] [-] apscheduler: pre-existing line\n",
            encoding="utf-8",
        )

        _setup_logging(_settings(tmp_path))

        text = log.read_text(encoding="utf-8")
        assert "pre-existing line" in text, "must append, not truncate the existing log"
        assert "sublarr-instance:" in text, (
            "an upgraded instance with a populated log file must still be identifiable"
        )

    def test_repeated_setup_stamps_the_same_file_only_once(self, restore_root_logger, tmp_path):
        # _setup_logging re-runs on every config save. Stamping per call would
        # bury the log in fingerprints — which is why the too-narrow
        # empty-file-only check existed in the first place.
        import app_logging

        app_logging._stamped_log_paths.clear()
        for _ in range(4):
            _setup_logging(_settings(tmp_path))

        text = (tmp_path / "sublarr.log").read_text(encoding="utf-8")
        assert text.count("sublarr-instance:") == 1

    def test_changing_the_log_path_stamps_the_new_file(self, restore_root_logger, tmp_path):
        import app_logging

        app_logging._stamped_log_paths.clear()
        _setup_logging(_settings(tmp_path))

        second = tmp_path / "moved"
        second.mkdir()
        _setup_logging(_settings(second))

        assert "sublarr-instance:" in (second / "sublarr.log").read_text(encoding="utf-8")

    def test_fingerprint_failure_never_breaks_logging(self, restore_root_logger, tmp_path):
        # Diagnostics must never be able to take down the thing they describe.
        from unittest.mock import patch

        with patch("app_logging._fingerprint_payload", side_effect=RuntimeError("boom")):
            _setup_logging(_settings(tmp_path))
            logging.getLogger("probe").warning("still logging")

        text = (tmp_path / "sublarr.log").read_text(encoding="utf-8")
        assert "still logging" in text


class TestFingerprintSurvivesTheTwoPhaseStart:
    """`mode=` must describe the instance, not the half-loaded config.

    Startup reads its configuration in two phases: ENV and defaults first,
    then the `config_entries` overlay from the database. `sonarr_url` is a UI
    field, so it exists ONLY in phase two. Stamping the fingerprint during
    phase one therefore reported `mode=unconfigured` on an instance with
    Sonarr wired up — the single field the stamp exists to answer, wrong on
    exactly the installs that ask for support. Seen on RC 1.11.0-rc.3; every
    unit test until then handed `_setup_logging` a fully-populated settings
    object and so could not reproduce it.
    """

    def test_startup_stamp_names_arr_mode_configured_only_in_the_database(
        self, restore_root_logger, temp_db, tmp_path
    ):
        import app_logging
        import config_singleton
        from app import create_app
        from app_shutdown import shutdown_event_dispatchers
        from db.config import save_config_entry

        os.environ["SUBLARR_LOG_FILE"] = str(tmp_path / "seed" / "sublarr.log")
        os.environ["SUBLARR_LOG_LEVEL"] = "INFO"
        config_singleton._settings = None

        # Phase one of the real story: an operator configures Sonarr through
        # the UI, which lands in config_entries and nowhere else.
        seed = create_app(testing=True)
        try:
            with seed.app_context():
                save_config_entry("sonarr_url", "http://sonarr:8989")
        finally:
            shutdown_event_dispatchers(seed)

        # Phase two: the container restarts against that database. A genuinely
        # fresh process — drop the cached singleton and the per-path stamp
        # guard so nothing carries over from the seed app.
        log_file = tmp_path / "config" / "sublarr.log"
        os.environ["SUBLARR_LOG_FILE"] = str(log_file)
        config_singleton._settings = None
        app_logging._stamped_log_paths.clear()

        app = create_app(testing=True)
        try:
            stamps = [
                line
                for line in log_file.read_text(encoding="utf-8").splitlines()
                if "sublarr-instance:" in line
            ]
        finally:
            shutdown_event_dispatchers(app)

        assert len(stamps) == 1, f"exactly one startup stamp expected, got {len(stamps)}"
        assert "mode=arr" in stamps[0], (
            "the startup stamp must be written after the config_entries overlay, "
            f"otherwise it reports an unconfigured instance: {stamps[0]}"
        )

    def test_rollover_stamp_reflects_config_saved_since_startup(
        self, restore_root_logger, tmp_path
    ):
        """A rollover weeks later must describe the instance as it is now.

        `sonarr_url` is not a logging key, so saving it never rebuilds the
        handler. A payload frozen at handler-construction time would keep
        re-stating the startup answer for the whole uptime.
        """
        import config_singleton

        boot = _settings(tmp_path, level="INFO")
        boot.standalone_enabled = False
        boot.sonarr_url = ""
        config_singleton._settings = boot
        _setup_logging(boot)

        live = _settings(tmp_path, level="INFO")
        live.standalone_enabled = False
        live.sonarr_url = "http://sonarr:8989"
        config_singleton._settings = live

        _rotating_handler().doRollover()

        first = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()[0]
        assert "mode=arr" in first


class TestRotatedLogPaths:
    """Consumers of the rotated log files must follow the configured backup count.

    `routes/system/support.py` hardcoded `range(1, 4)` in three places — the
    top-error parser, the support ZIP, and the redaction preview. That matched
    exactly while backupCount was itself hardcoded to 3. Once rotation became
    configurable (default 5, up to 20), all three silently skipped every file
    from `.4` on, so the support bundle a user sends would be missing log
    history that exists on disk.
    """

    def test_lists_the_active_file_plus_one_entry_per_backup(self, tmp_path):
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 5
        paths = rotated_log_candidates(settings)

        base = str(tmp_path / "sublarr.log")
        assert paths == [base] + [f"{base}.{i}" for i in range(1, 6)]

    def test_follows_a_raised_backup_count(self, tmp_path):
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 20
        assert len(rotated_log_candidates(settings)) == 21

    def test_applies_the_same_clamping_as_the_handler(self, tmp_path):
        # A junk value must not produce a zero-length or absurd candidate list.
        from app_logging import rotated_log_candidates

        settings = _settings(tmp_path)
        settings.log_backup_count = 999
        assert len(rotated_log_candidates(settings)) == 1 + LOG_BACKUP_COUNT_MAX

        settings.log_backup_count = "nonsense"
        assert len(rotated_log_candidates(settings)) == 1 + LOG_BACKUP_COUNT_DEFAULT

    def test_support_module_does_not_hardcode_a_rotation_depth(self):
        """Guard the actual defect: a literal range(1, 4) over the log path."""
        from pathlib import Path

        import routes.system.support as support_mod

        source = Path(support_mod.__file__).read_text(encoding="utf-8")
        assert "range(1, 4)" not in source, (
            "support.py must derive rotated log paths from the configured backup "
            "count, not a hardcoded depth"
        )


def test_logging_config_keys_cover_every_log_setting():
    """Every `log_*` setting must be in LOGGING_CONFIG_KEYS.

    Two call sites re-run _setup_logging only when a logging-relevant key was
    among the changed config entries: the startup DB-overlay in app.py and the
    live-apply on config save in routes/config/core.py. Both used a hardcoded
    ("log_level", "log_file", "log_format") triple, so log_max_size_mb and
    log_backup_count were declared, persisted, read by _setup_logging — and the
    re-apply still never fired for them. Unit tests that call _setup_logging
    directly cannot catch that gap; this one can.
    """
    from app_logging import LOGGING_CONFIG_KEYS
    from config_settings import BootSettings, UISettings

    declared = {
        name
        for model in (BootSettings, UISettings)
        for name in model.model_fields
        if name.startswith("log_")
    }
    missing = declared - LOGGING_CONFIG_KEYS
    assert not missing, (
        f"log settings not covered by LOGGING_CONFIG_KEYS: {sorted(missing)} — "
        "changing them via the UI would not re-apply the logging setup"
    )


def _rotating_handler():
    """The RotatingFileHandler installed by _setup_logging."""
    from logging.handlers import RotatingFileHandler

    handlers = [h for h in logging.getLogger().handlers if isinstance(h, RotatingFileHandler)]
    assert handlers, "RotatingFileHandler must be installed"
    return handlers[-1]


class TestLogRotationConfig:
    """PUT /api/v1/logs/rotation persisted log_max_size_mb / log_backup_count and
    promised "Changes take effect on next application restart", but nothing ever
    read them: _setup_logging hardcoded 5 MB / 3. The setting was a placebo, and
    the API even advertised defaults (10 MB / 5) that did not match the real
    behaviour. This matters for support: at DEBUG a wanted-search burst writes
    ~8k records/min (see module docstring), so the retention window is minutes
    and raising it is the user's only lever.
    """

    def test_configured_max_size_is_applied(self, restore_root_logger, tmp_path):
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 20
        _setup_logging(settings)

        assert _rotating_handler().maxBytes == 20 * 1024 * 1024

    def test_configured_backup_count_is_applied(self, restore_root_logger, tmp_path):
        settings = _settings(tmp_path)
        settings.log_backup_count = 7
        _setup_logging(settings)

        assert _rotating_handler().backupCount == 7

    def test_defaults_match_what_the_api_advertises(self, restore_root_logger, tmp_path):
        # GET /logs/rotation falls back to 10 MB / 5 when unset; the installed
        # handler must agree, or the UI reports a window the app does not use.
        _setup_logging(_settings(tmp_path))

        handler = _rotating_handler()
        assert handler.maxBytes == 10 * 1024 * 1024
        assert handler.backupCount == 5

    def test_zero_max_size_does_not_disable_rotation(self, restore_root_logger, tmp_path):
        # RotatingFileHandler treats maxBytes=0 as "never roll over", so a 0 in
        # config_entries would silently grow the log without bound — the worst
        # possible outcome for a setting meant to bound disk use.
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 0
        _setup_logging(settings)

        assert _rotating_handler().maxBytes >= 1024 * 1024

    def test_out_of_range_values_are_clamped_to_the_api_bounds(self, restore_root_logger, tmp_path):
        # config_entries is writable outside the route's 1..100 / 1..20 checks
        # (direct DB edit, or a value written by another version).
        settings = _settings(tmp_path)
        settings.log_max_size_mb = 5000
        settings.log_backup_count = -3
        _setup_logging(settings)

        handler = _rotating_handler()
        assert handler.maxBytes == 100 * 1024 * 1024
        assert handler.backupCount == 1

    def test_non_numeric_value_falls_back_to_the_default(self, restore_root_logger, tmp_path):
        # config_entries stores strings; a corrupt row must not stop logging.
        settings = _settings(tmp_path)
        settings.log_max_size_mb = "not-a-number"
        _setup_logging(settings)

        assert _rotating_handler().maxBytes == 10 * 1024 * 1024


def test_ws_handler_skips_format_when_no_clients():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {}  # no namespace → no clients
    handler = SocketIOLogHandler(sio)
    handler.format = MagicMock(side_effect=AssertionError("format ran with zero clients"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_not_called()


def test_ws_handler_emits_when_client_connected():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {"logs": {"sid1": True}}}
    handler = SocketIOLogHandler(sio)
    handler.setFormatter(logging.Formatter("%(message)s"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_called_once()


def test_ws_handler_emits_to_logs_room_only():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {"logs": {"sid1": True}}}
    handler = SocketIOLogHandler(sio)
    handler.setFormatter(logging.Formatter("%(message)s"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)

    _, kwargs = sio.emit.call_args
    assert kwargs.get("to") == "logs", "log_entry must be scoped to the logs room"


def test_ws_handler_skips_when_logs_room_empty():
    from unittest.mock import MagicMock

    from app_logging import SocketIOLogHandler

    sio = MagicMock()
    sio.server.manager.rooms = {"/": {None: {"sid1": True}}}  # connected, not subscribed
    handler = SocketIOLogHandler(sio)
    handler.format = MagicMock(side_effect=AssertionError("formatted for empty room"))

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)
    sio.emit.assert_not_called()
