"""Legacy-encoded subtitles must reach disk as readable UTF-8.

Providers (and the catalog bundles, which say so in their own comments) hand
Sublarr the subtitle's raw bytes and leave the encoding to the host. The
sanitizer used to decode them as UTF-8 with ``errors="replace"`` before anything
looked at the encoding, so a Windows-1252 "Grüße" was written as "Gr��e" and the
repair pass's chardet fallback never got to see the original bytes.
"""

import pytest

from subtitle_encoding import decode_subtitle_bytes, detect_encoding, ensure_utf8
from subtitle_normalise import normalise_downloaded_content
from subtitle_sanitizer import sanitize_subtitle

_SAMPLES = {
    "cp1252": "„Grüße“ – sagte er… Das kostet 5 €. Über die Brücke.",
    "cp1250": "Příliš žluťoučký kůň úpěl ďábelské ódy. Dobrý den.",
    "cp1251": "Привет мир. Как дела? Всё хорошо, спасибо большое.",
    "cp1253": "Γειά σου κόσμε. Τι κάνεις; Όλα καλά, ευχαριστώ πολύ.",
    "cp1254": "Günaydın dünya. Nasılsın? Her şey yolunda, teşekkürler.",
}


def _srt(text: str, cues: int = 3) -> str:
    return "".join(
        f"{i}\n00:00:0{i},000 --> 00:00:0{i},900\n{text}\n\n" for i in range(1, cues + 1)
    )


def _ass(text: str) -> str:
    return (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour,"
        " BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle,"
        " BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{text}\n"
    )


class TestEnsureUtf8:
    def test_valid_utf8_is_returned_unchanged(self):
        raw = _srt("Grüße").encode("utf-8")
        assert ensure_utf8(raw) is raw

    def test_utf8_bom_is_left_alone(self):
        # BOM stripping is the repair pass's job; the hash of BOM files must not move.
        raw = b"\xef\xbb\xbf" + _srt("Grüße").encode("utf-8")
        assert ensure_utf8(raw) is raw

    @pytest.mark.parametrize("encoding", sorted(_SAMPLES))
    def test_legacy_codepage_is_transcoded(self, encoding):
        text = _srt(_SAMPLES[encoding])
        assert ensure_utf8(text.encode(encoding)).decode("utf-8") == text

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
    def test_utf16_is_transcoded(self, encoding):
        text = _srt("Grüße aus der Straße")
        out = ensure_utf8(text.encode(encoding))
        assert out.decode("utf-8").lstrip("﻿") == text

    def test_empty_is_empty(self):
        assert ensure_utf8(b"") == b""


def test_decode_falls_back_without_raising():
    # Bytes that are not text in any encoding still come back as a str.
    assert isinstance(decode_subtitle_bytes(bytes(range(256))), str)


class TestSanitizerKeepsLegacyText:
    @pytest.mark.parametrize("encoding", sorted(_SAMPLES))
    def test_srt(self, encoding):
        text = _SAMPLES[encoding]
        out = sanitize_subtitle(_srt(text).encode(encoding), "srt").decode("utf-8")
        assert text in out
        assert "�" not in out

    @pytest.mark.parametrize("encoding", sorted(_SAMPLES))
    def test_ass(self, encoding):
        text = _SAMPLES[encoding]
        out = sanitize_subtitle(_ass(text).encode(encoding), "ass").decode("utf-8")
        assert text in out
        assert "�" not in out

    def test_utf16_srt_passes_the_format_check(self):
        # validate_content_type looked at the raw UTF-16 bytes, saw b"\xff\xfe1\x00",
        # and rejected a perfectly good subtitle as "does not match srt".
        out = sanitize_subtitle(_srt("Hallo Welt").encode("utf-16"), "srt")
        assert b"Hallo Welt" in out

    def test_utf16_ass_passes_the_format_check(self):
        out = sanitize_subtitle(_ass("Hallo Welt").encode("utf-16"), "ass")
        assert b"Hallo Welt" in out

    def test_unknown_format_bytes_pass_through_untouched(self):
        raw = "Grüße".encode("cp1252")
        assert sanitize_subtitle(raw, "unknown") == raw


@pytest.mark.parametrize("encoding", sorted(_SAMPLES))
def test_download_normalisation_keeps_legacy_text(app_ctx, encoding):
    text = _SAMPLES[encoding]
    out = normalise_downloaded_content(_srt(text).encode(encoding), "srt").decode("utf-8")
    assert text in out
    assert "�" not in out


def test_normalisation_of_utf8_is_unchanged_by_the_transcode(app_ctx):
    """Stored pristine hashes are of normalised UTF-8; they must not move."""
    raw = _srt("Grüße").encode("utf-8")
    assert normalise_downloaded_content(raw, "srt") == normalise_downloaded_content(
        normalise_downloaded_content(raw, "srt"), "srt"
    )


def test_legacy_text_survives_with_repair_disabled(app_ctx, monkeypatch):
    """The transcode is not part of the optional repair pass."""
    import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "enable_subtitle_repair", False, raising=False)
    text = _SAMPLES["cp1252"]
    out = normalise_downloaded_content(_srt(text).encode("cp1252"), "srt").decode("utf-8")
    assert text in out


class TestLanguageGuides:
    """Short files are where chardet guesses wildly; the language does not."""

    @pytest.mark.parametrize(
        ("language", "encoding", "text"),
        [
            ("de", "cp1252", "Grüße!"),
            ("fr", "cp1252", "Ça va très bien."),
            ("es", "cp1252", "Mañana."),
            ("ru", "cp1251", "Да."),
            ("cs", "cp1250", _SAMPLES["cp1250"]),
            ("el", "cp1253", _SAMPLES["cp1253"]),
            ("tr", "cp1254", _SAMPLES["cp1254"]),
            ("he", "cp1255", "שלום עולם. מה שלומך?"),
            ("pt-BR", "cp1252", "Não, obrigação."),
        ],
    )
    def test_one_cue(self, language, encoding, text):
        raw = _srt(text, cues=1).encode(encoding)
        assert decode_subtitle_bytes(raw, language=language) == _srt(text, cues=1)

    def test_chinese_gbk_and_big5_are_told_apart(self):
        text = _srt("你好，世界。今天天氣很好，我們去公園散步吧。", cues=20)
        for encoding in ("gbk", "big5"):
            assert decode_subtitle_bytes(text.encode(encoding), language="zh") == text

    def test_japanese_shift_jis(self):
        text = _srt("こんにちは、世界。今日はいい天気ですね。", cues=20)
        assert decode_subtitle_bytes(text.encode("cp932"), language="ja") == text

    def test_utf8_bom_in_front_of_cp1252_body(self):
        text = _srt("Grüße aus der Straße")
        raw = b"\xef\xbb\xbf" + text.encode("cp1252")
        assert decode_subtitle_bytes(raw, language="de") == text


class TestProviderHint:
    def test_real_hint_wins(self):
        text = _srt("שלום עולם. מה שלומך?", cues=1)
        assert decode_subtitle_bytes(text.encode("cp1255"), hint="windows-1255") == text

    def test_latin1_placeholder_is_ignored(self):
        # greeksubs says "latin-1" for every body that is not UTF-8.
        text = _srt(_SAMPLES["cp1253"])
        raw = text.encode("cp1253")
        assert decode_subtitle_bytes(raw, language="el", hint="latin-1") == text

    def test_unknown_hint_is_ignored(self):
        text = _srt("Grüße")
        assert decode_subtitle_bytes(text.encode("cp1252"), "de", hint="no-such-codec") == text


class TestWideUnicode:
    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32"])
    def test_detected(self, encoding):
        from subtitle_encoding import is_wide_unicode

        assert is_wide_unicode(_srt("Hallo").encode(encoding))

    @pytest.mark.parametrize("encoding", ["utf-8", "cp1252", "cp1251"])
    def test_not_detected(self, encoding):
        from subtitle_encoding import is_wide_unicode

        assert not is_wide_unicode(_srt(_SAMPLES.get(encoding, "Grüße")).encode(encoding))

    def test_binary_is_not_wide_unicode(self):
        from subtitle_encoding import is_wide_unicode

        assert not is_wide_unicode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _save(tmp_path, monkeypatch, content, language="de"):
    from providers.base import SubtitleFormat, SubtitleResult
    from providers.download_manager import save_subtitle

    monkeypatch.setattr("security_utils.is_safe_path", lambda *a, **kw: True, raising=False)
    result = SubtitleResult(
        provider_name="p",
        subtitle_id="1",
        language=language,
        format=SubtitleFormat.SRT,
        content=content,
    )
    from pathlib import Path

    return Path(save_subtitle(result, str(tmp_path / f"ep.{language}.srt"))).read_text("utf-8")


class TestSaveSubtitle:
    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
    def test_utf16_download_is_saved_as_utf8(self, app_ctx, tmp_path, monkeypatch, encoding):
        text = "Grüße aus der Straße"
        assert text in _save(tmp_path, monkeypatch, _srt(text).encode(encoding))

    def test_cp1251_download_keeps_its_cyrillic(self, app_ctx, tmp_path, monkeypatch):
        text = "Да."
        assert text in _save(tmp_path, monkeypatch, _srt(text).encode("cp1251"), language="ru")

    def test_language_check_sees_mislabelled_legacy_chinese(self, app_ctx, tmp_path, monkeypatch):
        # Prod 2026-09-06 class: Chinese delivered as "German". In GBK the letters
        # used to be U+FFFD by the time the check looked, so it always passed.
        raw = _srt("你好，世界。今天天氣很好，我們去公園散步吧。", cues=20).encode("gbk")
        with pytest.raises(RuntimeError, match="rejected"):
            _save(tmp_path, monkeypatch, raw, language="de")

    def test_binary_signature_still_rejected(self, app_ctx, tmp_path, monkeypatch):
        with pytest.raises(RuntimeError, match="validation"):
            _save(tmp_path, monkeypatch, b"MZ\x90\x00" + bytes(range(256)) * 4)


class TestUpload:
    def test_cp1252_upload_keeps_umlauts(self):
        from services.subtitle_upload import prepare_upload

        text = "Grüße aus der Straße"
        content, ext = prepare_upload("Movie.srt", _srt(text).encode("cp1252"), "de")
        assert ext == "srt"
        assert text in content.decode("utf-8")

    @pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
    def test_utf16_upload_is_accepted(self, encoding):
        from services.subtitle_upload import prepare_upload

        content, ext = prepare_upload("Movie.srt", _srt("Hallo Welt").encode(encoding), "de")
        assert ext == "srt"
        assert b"Hallo Welt" in content

    def test_utf16_ass_upload_is_detected_as_ass(self):
        from services.subtitle_upload import prepare_upload

        _content, ext = prepare_upload("Movie.ass", _ass("Hallo Welt").encode("utf-16"), "de")
        assert ext == "ass"


class TestSizeLimitAfterConversion:
    """The limit applies to the UTF-8 that is written, on every path."""

    def _big_srt(self, mb: float) -> str:
        cue = "1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела? Всё хорошо.\n\n"
        return cue * int(mb * 1024 * 1024 / len(cue.encode("utf-8")))

    def test_utf16_download_and_repair_agree(self, app_ctx):
        from subtitle_sanitizer import _MAX_SUBTITLE_BYTES

        text = self._big_srt(_MAX_SUBTITLE_BYTES / 1024 / 1024 * 0.9)
        raw = text.encode("utf-16")
        assert len(raw) > _MAX_SUBTITLE_BYTES  # only the UTF-16 is over
        # The repair path hands the raw provider bytes to the normaliser.
        assert normalise_downloaded_content(raw, "srt", language="ru")

    def test_legacy_file_that_grows_past_the_limit_is_rejected(self):
        from subtitle_sanitizer import _MAX_SUBTITLE_BYTES

        text = self._big_srt(_MAX_SUBTITLE_BYTES / 1024 / 1024 * 1.1)
        raw = text.encode("cp1251")
        assert len(raw) < _MAX_SUBTITLE_BYTES  # under the limit as it came
        with pytest.raises(ValueError, match="too large"):
            sanitize_subtitle(raw, "srt", language="ru")


def test_repair_scan_hashes_legacy_files_like_the_dedup_scan(tmp_path):
    """A dedup scan fills subtitle_hashes; the repair scan compares against it."""
    from dedup_engine import compute_subtitle_hash
    from services.repair.scanner import content_hash

    path = tmp_path / "Show.S01E01.de.srt"
    path.write_bytes("1\r\n00:00:01,000 --> 00:00:02,000\r\nGrüße\r\n".encode("cp1252"))
    assert content_hash(str(path)) == compute_subtitle_hash(str(path))["content_hash"]


@pytest.mark.parametrize(
    ("encoding", "text"),
    [
        ("cp1250", "Dobar dan, kako ste? Hvala, dobro sam. Šta ima novo, čoveče?"),
        ("cp1251", "Добар дан, како сте? Хвала, добро сам. Шта има ново, човече?"),
    ],
)
def test_serbian_in_either_script(encoding, text):
    raw = _srt(text).encode(encoding)
    decoded = detect_encoding(raw, language="sr")
    assert decoded.text == _srt(text)
    assert decoded.basis == "language"
