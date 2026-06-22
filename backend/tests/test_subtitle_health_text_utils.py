from services.subtitle_health import text_utils


def test_decode_with_confidence_utf8():
    text, enc, conf = text_utils.decode_with_confidence("Schön".encode())
    assert "Schön" in text
    assert enc == "utf-8"
    assert conf >= 0.9


def test_decode_with_confidence_latin1_fallback():
    text, enc, conf = text_utils.decode_with_confidence("Schön".encode("cp1252"))
    # cp1252 'ö' is invalid utf-8; must not crash and must recover the text
    assert "Sch" in text
    assert enc != "utf-8"


def test_extract_cue_text_srt_drops_numbers_and_timestamps():
    raw = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello there.\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nSecond line.\n"
    )
    text = text_utils.extract_cue_text_srt(raw)
    assert "Hello there." in text
    assert "Second line." in text
    assert "00:00:01" not in text
    assert "-->" not in text


def test_strip_ass_tags_for_analysis():
    assert text_utils.strip_ass_tags("{\\i1}Hallo{\\i0}\\Nwelt") == "Hallo welt"
