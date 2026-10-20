from services.subtitle_health.fixers import reencode


def test_reencodes_cp1252_to_utf8():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n".encode("cp1252")
    out = reencode.reencode_bytes(raw)
    assert out.decode("utf-8") == "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n"


def test_strips_bom():
    raw = b"\xef\xbb\xbf" + b"Hallo"
    out = reencode.reencode_bytes(raw)
    assert not out.startswith(b"\xef\xbb\xbf")


def test_idempotent_on_clean_utf8():
    raw = "Schön".encode()
    assert reencode.reencode_bytes(reencode.reencode_bytes(raw)) == reencode.reencode_bytes(raw)


def test_cyrillic_is_not_turned_into_latin_mojibake():
    # cp1252 decodes any byte string, so it used to "win" for cp1251 Russian too.
    raw = "1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела?\n".encode("cp1251")
    out = reencode.reencode_bytes(raw, language="ru")
    assert "Привет, как дела?" in out.decode("utf-8")


def test_utf16_is_reencoded_without_nuls():
    raw = "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n".encode("utf-16")
    out = reencode.reencode_bytes(raw)
    assert out.decode("utf-8") == "1\n00:00:01,000 --> 00:00:02,000\nSchön warm.\n"


def test_sidecar_with_language_in_name_is_rewritten(tmp_path, monkeypatch):
    monkeypatch.setattr(reencode, "backup_sidecar", lambda p: str(p) + ".trash")
    monkeypatch.setattr("services.subtitle_health.store.record_fix", lambda **kw: 7)
    path = tmp_path / "Show.S01E01.ru.srt"
    path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела?\n".encode("cp1251"))
    assert reencode.apply_to_sidecar(str(path))["changed"] is True
    assert "Привет" in path.read_text("utf-8")


def test_sidecar_without_language_is_left_alone(tmp_path):
    # Without a language the guess is chardet's, which reads short files as Big5.
    path = tmp_path / "Show.S01E01.srt"
    raw = "1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела?\n".encode("cp1251")
    path.write_bytes(raw)
    assert reencode.apply_to_sidecar(str(path)) == {
        "changed": False,
        "reason": "decode confidence too low",
    }
    assert path.read_bytes() == raw
