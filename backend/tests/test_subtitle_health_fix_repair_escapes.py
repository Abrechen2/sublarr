from services.subtitle_health.fixers import repair_escapes


def test_repairs_literal_escapes(tmp_path):
    p = tmp_path / "x.de.srt"
    p.write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\nDu hast erkannt\\Nwie gut?\n")
    new = repair_escapes.repair_bytes(p.read_bytes(), codec="srt")
    assert b"\\N" not in new
    assert b"erkannt\nwie gut?" in new


def test_strips_h_and_tags():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\n{\\an8}Oben\\hrechts\n"
    new = repair_escapes.repair_bytes(raw, codec="srt")
    assert b"{\\an8}" not in new
    assert b"\\h" not in new


def test_idempotent():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nText\\Nmehr\n"
    once = repair_escapes.repair_bytes(raw, codec="srt")
    twice = repair_escapes.repair_bytes(once, codec="srt")
    assert once == twice


def test_ass_codec_keeps_tags():
    raw = b"[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\i1}Hi{\\i0}\n"
    new = repair_escapes.repair_bytes(raw, codec="ass")
    assert b"{\\i1}" in new  # never strip override tags on native ASS
