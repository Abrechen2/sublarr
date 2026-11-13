"""A download whose dialogue is another Latin-script language is refused.

Prod 2026-11-08: 131 downloaded ``.de``/``.en`` files held Indonesian,
Vietnamese, Catalan, Spanish or English under ``.de``. The script check passes
them all — the letters are Latin either way.
"""

from __future__ import annotations

import pytest

from subtitle_language import language_mismatch

_INDONESIAN = [
    "Aku tidak tahu apa yang harus kulakukan sekarang.",
    "Kenapa kamu tidak memberitahuku sejak awal?",
    "Kita harus pergi dari sini sebelum mereka datang.",
    "Terima kasih sudah menolongku kemarin malam.",
    "Apakah kamu yakin ini jalan yang benar?",
    "Jangan khawatir, aku akan segera kembali.",
    "Dia bilang dia akan menunggu di depan sekolah.",
    "Sudah lama sekali aku tidak bertemu denganmu.",
]
_VIETNAMESE = [
    "Tôi không biết phải làm gì bây giờ.",
    "Tại sao cậu không nói với tôi từ đầu?",
    "Chúng ta phải rời khỏi đây trước khi họ đến.",
    "Cảm ơn vì đã giúp tôi tối hôm qua.",
    "Cậu có chắc đây là con đường đúng không?",
    "Đừng lo, tôi sẽ quay lại ngay.",
    "Cô ấy nói sẽ đợi ở trước cổng trường.",
    "Đã lâu lắm rồi tôi không gặp cậu.",
]
_ENGLISH = [
    "I don't know what I'm supposed to do now.",
    "Why didn't you tell me from the beginning?",
    "We have to get out of here before they come.",
    "Thank you for helping me last night.",
    "Are you sure this is the right way?",
    "Don't worry, I'll be right back.",
    "She said she would wait in front of the school.",
    "It's been such a long time since I last saw you.",
]
_GERMAN = [
    "Ich weiß nicht, was ich jetzt tun soll.",
    "Warum hast du es mir nicht von Anfang an gesagt?",
    "Wir müssen hier weg, bevor sie kommen.",
    "Danke, dass du mir gestern Abend geholfen hast.",
    "Bist du sicher, dass das der richtige Weg ist?",
    "Keine Sorge, ich bin gleich zurück.",
    "Sie sagte, sie würde vor der Schule warten.",
    "Es ist so lange her, dass ich dich gesehen habe.",
]


def _srt(lines: list[str], repeat: int = 6) -> bytes:
    cues = [line for _ in range(repeat) for line in lines]
    return "".join(
        f"{i}\n00:{i // 60:02d}:{i % 60:02d},000 --> 00:{i // 60:02d}:{i % 60:02d},900\n{text}\n\n"
        for i, text in enumerate(cues, start=1)
    ).encode("utf-8")


@pytest.mark.parametrize(
    ("lines", "claimed", "detected"),
    # Indonesian and Malay share most of their words; either is "not English".
    [(_INDONESIAN, "en", ("id", "ms")), (_VIETNAMESE, "en", ("vi",)), (_ENGLISH, "de", ("en",)),
     (_GERMAN, "eng", ("de",))],
)  # fmt: skip
def test_another_language_under_the_name_is_reported(lines, claimed, detected):
    reason = language_mismatch(_srt(lines), claimed)
    assert reason is not None and any(f"reads as {code}" in reason for code in detected)


@pytest.mark.parametrize(
    ("lines", "claimed"), [(_ENGLISH, "en"), (_GERMAN, "de"), (_GERMAN, "ger")]
)
def test_the_right_language_passes(lines, claimed):
    assert language_mismatch(_srt(lines), claimed) is None


def test_short_text_gets_no_verdict():
    assert language_mismatch(_srt(_INDONESIAN, repeat=1), "en") is None


def test_a_language_outside_the_set_is_not_judged():
    assert language_mismatch(_srt(_INDONESIAN), "fi") is None


def test_unreadable_content_gets_no_verdict():
    assert language_mismatch(b"\x00\x01garbage", "en") is None


def test_save_subtitle_refuses_the_mislabelled_download(app_ctx, tmp_path, monkeypatch):
    from providers.base import SubtitleFormat, SubtitleResult
    from providers.download_manager import save_subtitle

    monkeypatch.setattr("security_utils.is_safe_path", lambda *a, **kw: True, raising=False)
    result = SubtitleResult(
        provider_name="animetosho",
        subtitle_id="683348:3085253",
        language="en",
        format=SubtitleFormat.SRT,
        content=_srt(_VIETNAMESE),
    )
    with pytest.raises(RuntimeError, match="rejected"):
        save_subtitle(result, str(tmp_path / "ep.en.srt"))
    assert not (tmp_path / "ep.en.srt").exists()


def test_romanised_song_lyrics_do_not_vote():
    """Prod: an English ASS whose "OP Roma" karaoke read as Indonesian."""
    lyrics = "tada hashiru dakesa tekipaki patapata minna atsumatte hitotsu no shigoto"
    events = "".join(
        f"Dialogue: 0,0:0{i // 60}:{i % 60:02d}.00,0:0{i // 60}:{i % 60:02d}.90,OP Roma,,0,0,0,,"
        f"{{\\k20}}{lyrics} {i}\n"
        for i in range(300)
    ) + "".join(
        f"Dialogue: 0,0:1{i // 60}:{i % 60:02d}.00,0:1{i // 60}:{i % 60:02d}.90,Default,,0,0,0,,"
        f"{line}\n"
        for i, line in enumerate(_ENGLISH * 6)
    )
    ass = (
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
        "Style: Default,Arial,20\nStyle: OP Roma,Arial,20\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" + events
    )
    assert language_mismatch(ass.encode("utf-8"), "en") is None


@pytest.mark.parametrize(
    "style", ["OP Roma", "Neo_ED_English", "Grp_Karaoke", "Insert_Song", "RomajiED2", "OP1-Romaji2"]
)
def test_lyrics_styles_are_recognised_with_underscores(style):
    """A plain \\b misses "Neo_ED_English": "_" is a word character."""
    from subtitle_language import _LYRICS_STYLE

    assert _LYRICS_STYLE.search(style)


@pytest.mark.parametrize("style", ["Default", "Fred", "Opening Credits Dialogue", "Edgar"])
def test_dialogue_styles_are_not_lyrics(style):
    from subtitle_language import _LYRICS_STYLE

    assert not _LYRICS_STYLE.search(style)
