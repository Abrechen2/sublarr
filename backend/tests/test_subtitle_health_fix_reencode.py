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
