"""subtitle_script — does a subtitle's writing system match the language it claims?

Prod 2026-09-07: eighteen ``.de.srt`` files held Arabic, Chinese or Japanese
text. Three came from a provider whose "German" upload was Chinese, the rest
from a spring-2026 extractor that wrote the first foreign track under the
target-language name. Nothing between the container, the provider, the
translator and the player ever looked at the letters.
"""

from __future__ import annotations

import pytest

from subtitle_script import expected_script, find_script_mismatch, script_mismatch

ARABIC = "‫كانت هناك حرب كبيرة ذات يوم. واصل المحاربون الشهيرون القتال، مع قناعاتهم وطموحاتهم"
CHINESE = (
    "彷彿在夢境中遨遊 因淡淡的期待而心情雀躍 將胸口的光芒緊緊藏起 某天的日常變得格外令人懷念呢"
)
JAPANESE = (
    "今は昔、竹取の翁といふものありけり。野山にまじりて竹を取りつつ、よろづのことに使ひけり。"
)
GERMAN = (
    "Einst gab es einen großen Krieg. Berühmte Krieger kämpften mit ihren eigenen Überzeugungen."
)
ENGLISH = (
    "Once upon a time there was a great war. Famous warriors kept fighting with their own beliefs."
)


class TestExpectedScript:
    @pytest.mark.parametrize(
        "lang,script",
        [
            ("de", "latin"),
            ("ger", "latin"),
            ("en", "latin"),
            ("vi", "latin"),
            ("ru", "cyrillic"),
            ("ar", "arabic"),
            ("he", "hebrew"),
            ("el", "greek"),
            ("th", "thai"),
            ("ja", "cjk"),
            ("zh", "cjk"),
            ("zh-hans", "cjk"),
            ("ko", "cjk"),
            ("und", None),
            ("", None),
            ("xx", None),
        ],
    )
    def test_known_languages_map_to_a_script(self, lang, script):
        assert expected_script(lang) == script


class TestScriptMismatch:
    def test_arabic_text_under_a_german_name_is_a_mismatch(self):
        reason = script_mismatch(ARABIC * 2, "de")
        assert reason is not None
        assert "arabic" in reason and "latin" in reason

    def test_chinese_text_under_a_german_name_is_a_mismatch(self):
        assert script_mismatch(CHINESE * 2, "de") is not None

    def test_japanese_text_under_a_german_name_is_a_mismatch(self):
        assert script_mismatch(JAPANESE, "de") is not None

    def test_german_text_under_a_german_name_passes(self):
        assert script_mismatch(GERMAN, "de") is None

    def test_english_text_under_a_german_name_passes(self):
        """Wrong language, right script: not this check's job."""
        assert script_mismatch(ENGLISH, "de") is None

    def test_japanese_text_under_a_japanese_name_passes(self):
        assert script_mismatch(JAPANESE, "ja") is None

    def test_arabic_text_under_an_arabic_name_passes(self):
        assert script_mismatch(ARABIC * 2, "ar") is None

    def test_german_with_a_few_kanji_passes(self):
        """A German line quoting a sign in kanji is still German."""
        text = GERMAN + " Auf dem Schild steht 東京 (Tokyo)."
        assert script_mismatch(text, "de") is None

    def test_too_little_text_gives_no_opinion(self):
        assert script_mismatch("東京", "de") is None
        assert script_mismatch("", "de") is None

    def test_unknown_language_gives_no_opinion(self):
        assert script_mismatch(ARABIC * 2, "und") is None
        assert script_mismatch(ARABIC * 2, "") is None

    def test_romaji_under_a_japanese_name_gives_no_opinion(self):
        """CJK releases carry romaji, karaoke and English lines; the check
        does not judge them."""
        romaji = "Kimi no na wa nan desu ka. Boku wa kono machi ga suki desu. Arigatou gozaimasu."
        assert script_mismatch(romaji * 2, "ja") is None

    def test_chinese_under_a_russian_name_is_a_mismatch(self):
        assert script_mismatch(CHINESE * 2, "ru") is not None

    def test_ass_header_does_not_outvote_a_short_cjk_dialogue(self):
        ass = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour\n"
            "Style: Default,Arial,48,&H00FFFFFF,&H000000FF\n"
            "Style: Signs,Verdana,40,&H00FFFFFF,&H000000FF\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\an8}"
            + ARABIC
            + "\nDialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,"
            + ARABIC
            + "\n"
        )
        assert script_mismatch(ass, "de") is not None, "the Arabic cues decide, not the header"
        assert script_mismatch(ass, "ar") is None

    def test_utf16_sidecar_is_decoded_before_judging(self):
        from subtitle_script import decode_sample

        data = ("1\n00:00:01,000 --> 00:00:02,000\n" + GERMAN + "\n").encode("utf-16")
        assert script_mismatch(decode_sample(data), "de") is None
        assert script_mismatch(decode_sample((ARABIC * 2).encode("utf-16")), "de") is not None

    def test_srt_timing_and_markup_are_ignored(self):
        srt = (
            "1\n00:00:27,527 --> 00:00:30,655\n<i>" + ARABIC + "</i>\n\n"
            "2\n00:00:31,489 --> 00:00:37,245\n{\\an8}" + ARABIC + "\n"
        )
        assert script_mismatch(srt, "de") is not None


class TestFindScriptMismatch:
    def test_batch_of_chinese_lines_for_a_german_target_is_rejected(self):
        lines = [CHINESE[i : i + 12] for i in range(0, 48, 12)]
        assert find_script_mismatch(lines, "de") is not None

    def test_batch_of_german_lines_passes(self):
        lines = ["Das werde ich beschlagnahmen.", "Bist du bereit, loszufahren?", "Ich bin bereit."]
        assert find_script_mismatch(lines, "de") is None

    def test_none_entries_are_skipped(self):
        assert find_script_mismatch([None, "Ich bin bereit, das ist gut so.", None], "de") is None
