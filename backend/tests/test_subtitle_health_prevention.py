from subtitle_sanitizer import sanitize_srt_vtt_content


def test_sanitizer_repairs_literal_escapes():
    raw = b"1\n00:00:01,000 --> 00:00:02,000\nA\\NB\n"
    out = sanitize_srt_vtt_content(raw)
    assert b"\\N" not in out
    assert b"A\nB" in out
