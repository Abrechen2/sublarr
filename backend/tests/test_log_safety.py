"""Log injection: line breaks in logged values must not forge log records."""

import logging
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest

from app_logging import _setup_logging
from log_safety import LineBreakEscapeFilter, escape_line_breaks


def _record(msg, args):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)


def _filtered(msg, args):
    record = _record(msg, args)
    assert LineBreakEscapeFilter().filter(record) is True
    return record.getMessage()


class TestEscapeLineBreaks:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("a\nb", "a\\nb"),
            ("a\r\nb", "a\\r\\nb"),
            ("a b", "a\\u2028b"),
            ("a\x85b", "a\\x85b"),
            ("a\x0bb\x0cc", "a\\x0bb\\x0cc"),
        ],
    )
    def test_every_splitlines_boundary_is_escaped(self, raw, expected):
        assert escape_line_breaks(raw) == expected
        assert len(escape_line_breaks(raw).splitlines()) == 1

    def test_plain_text_is_unchanged(self):
        assert escape_line_breaks("/media/Show S01E01.mkv") == "/media/Show S01E01.mkv"


class TestLineBreakEscapeFilter:
    def test_string_argument_cannot_start_a_new_record(self):
        forged = "x.srt\n2026-10-25 12:00:00,000 [ERROR] [-] auth: admin login"
        message = _filtered("Translating %s", (forged,))
        assert message.splitlines() == [message]
        assert "\\n2026-10-25" in message

    def test_template_newlines_are_kept(self):
        # The template is code; a deliberate multi-line message stays one.
        assert _filtered("first\nsecond %s", ("v",)) == "first\nsecond v"

    def test_exception_and_path_arguments_are_escaped(self):
        message = _filtered("%s / %s", (ValueError("bad\nline"), PurePosixPath("/media/a\nb.srt")))
        assert message == "bad\\nline / /media/a\\nb.srt"

    def test_clean_exception_keeps_its_repr(self):
        exc = ValueError("clean")
        assert _filtered("%r", (exc,)) == repr(exc)

    def test_mapping_arguments(self):
        assert _filtered("%(p)s", ({"p": "a\nb"},)) == "a\\nb"

    def test_non_string_arguments_are_untouched(self):
        assert _filtered("%d items, %.1f s", (3, 1.5)) == "3 items, 1.5 s"

    def test_applied_once_per_record(self):
        record = _record("%s", ("a\nb",))
        f = LineBreakEscapeFilter()
        f.filter(record)
        f.filter(record)
        assert record.getMessage() == "a\\nb"


@pytest.fixture
def restore_root_logger():
    root = logging.getLogger()
    prev_level = root.level
    prev_handlers = list(root.handlers)
    yield
    for handler in list(root.handlers):
        if handler not in prev_handlers:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
    root.setLevel(prev_level)


def _settings(tmp_path):
    return SimpleNamespace(
        log_level="INFO", log_file=str(tmp_path / "sublarr.log"), log_format="text"
    )


class TestInstalledOnEveryHandler:
    def test_every_root_handler_carries_the_filter_once(self, restore_root_logger, tmp_path):
        for _ in range(2):
            _setup_logging(_settings(tmp_path))
        for handler in logging.getLogger().handlers:
            count = sum(isinstance(f, LineBreakEscapeFilter) for f in handler.filters)
            assert count == 1, handler

    def test_log_file_gets_one_line_per_record(self, restore_root_logger, tmp_path):
        _setup_logging(_settings(tmp_path))
        logging.getLogger("routes.translate").info(
            "Translating %s", "a.srt\n2026-01-01 00:00:00,000 [ERROR] [-] forged: yes"
        )
        for handler in logging.getLogger().handlers:
            handler.flush()

        lines = (tmp_path / "sublarr.log").read_text(encoding="utf-8").splitlines()
        hits = [ln for ln in lines if "Translating" in ln]
        assert len(hits) == 1
        assert not any(ln.startswith("2026-01-01 00:00:00,000 [ERROR]") for ln in lines)
