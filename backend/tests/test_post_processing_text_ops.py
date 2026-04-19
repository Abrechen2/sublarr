"""Plan B6 — text ops tests."""


def test_strip_html_removes_basic_tags(tmp_path):
    from post_processing.ops.text_ops import StripHtmlOp

    path = tmp_path / "x.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n<i>Italic</i> <b>Bold</b>\n",
        encoding="utf-8",
    )
    result = StripHtmlOp().execute(
        {
            "subtitle_path": str(path),
            "lang": "en",
            "video_path": "",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok
    content = path.read_text(encoding="utf-8")
    assert "<i>" not in content
    assert "<b>" not in content
    assert "Italic" in content
    assert "Bold" in content


def test_strip_html_noop_when_no_tags(tmp_path):
    from post_processing.ops.text_ops import StripHtmlOp

    path = tmp_path / "x.srt"
    original = "1\n00:00:01,000 --> 00:00:02,000\nPlain text\n"
    path.write_text(original, encoding="utf-8")
    result = StripHtmlOp().execute(
        {
            "subtitle_path": str(path),
            "lang": "en",
            "video_path": "",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok
    assert path.read_text(encoding="utf-8") == original


def test_remove_bom_op(tmp_path):
    from post_processing.ops.text_ops import RemoveBomOp

    path = tmp_path / "x.srt"
    path.write_bytes(b"\xef\xbb\xbf1\n00:00:01,000 --> 00:00:02,000\nHello\n")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    result = RemoveBomOp().execute(
        {
            "subtitle_path": str(path),
            "lang": "en",
            "video_path": "",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert b"Hello" in path.read_bytes()


def test_convert_encoding_op(tmp_path):
    from post_processing.ops.text_ops import ConvertEncodingOp

    path = tmp_path / "x.srt"
    # Write raw windows-1252 bytes: 'It' + 0x92 (right single quote) + 's a test.'
    # 0x92 is not valid UTF-8 on its own, which forces the op to re-detect + convert.
    path.write_bytes(b"It\x92s a test.")

    op = ConvertEncodingOp()
    result = op.execute(
        {
            "subtitle_path": str(path),
            "lang": "en",
            "video_path": "",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok
    # Result is decodable as utf-8
    path.read_text(encoding="utf-8")


def test_convert_encoding_noop_already_utf8(tmp_path):
    from post_processing.ops.text_ops import ConvertEncodingOp

    path = tmp_path / "x.srt"
    path.write_text("Plain ASCII content.", encoding="utf-8")
    original = path.read_bytes()
    result = ConvertEncodingOp().execute(
        {
            "subtitle_path": str(path),
            "lang": "en",
            "video_path": "",
            "score": 0,
            "trigger": "after_download",
        }
    )
    assert result.ok
    assert path.read_bytes() == original
