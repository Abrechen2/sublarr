"""Steps 2/4 of the wanted search follow the item's profile source (#80).

The provider-source steps searched, stored and translated with the global
``source_language``. A de->en profile on an en->de install therefore skipped
both steps outright: the same-language guard compared the en target with the
global en source, although the profile translates from German.
"""

from unittest.mock import MagicMock, patch

from tests.test_same_language_translation_guard import _step_ctx


def _profile_ctx(item_lang: str, global_source: str, profile_source: str) -> dict:
    ctx = _step_ctx(item_lang=item_lang, source_language=global_source)
    ctx["source_language"] = profile_source
    return ctx


class TestStepsUseTheProfileSource:
    def test_step2_searches_for_a_de_to_en_profile_on_an_en_install(self):
        from wanted_search.process import _try_source_ass_translation

        ctx = _profile_ctx(item_lang="en", global_source="en", profile_source="de")
        _try_source_ass_translation(ctx)
        ctx["manager"].search_and_download_best.assert_called_once()

    def test_step4_searches_for_a_de_to_en_profile_on_an_en_install(self):
        from wanted_search.process import _try_source_srt_translation

        ctx = _profile_ctx(item_lang="en", global_source="en", profile_source="de")
        _try_source_srt_translation(ctx)
        ctx["manager"].search_and_download_best.assert_called_once()

    def test_step2_skips_when_the_profile_source_equals_the_target(self):
        from wanted_search.process import _try_source_ass_translation

        ctx = _profile_ctx(item_lang="de", global_source="en", profile_source="de")
        assert _try_source_ass_translation(ctx) is None
        ctx["manager"].search_and_download_best.assert_not_called()


class TestItemSourceLanguage:
    def test_profile_source_wins(self):
        from wanted_search.process import _item_source_language

        settings = MagicMock(source_language="en")
        with patch(
            "services.mt_provisional._resolve_profile_for_item",
            return_value={"source_language": "de"},
        ):
            assert _item_source_language({"id": 1}, settings) == "de"

    def test_upper_case_profile_source_is_normalised(self):
        from wanted_search.process import _item_source_language

        settings = MagicMock(source_language="en")
        with patch(
            "services.mt_provisional._resolve_profile_for_item",
            return_value={"source_language": "DE"},
        ):
            assert _item_source_language({"id": 1}, settings) == "de"

    def test_global_source_without_a_profile_source(self):
        from wanted_search.process import _item_source_language

        settings = MagicMock(source_language="en")
        with patch("services.mt_provisional._resolve_profile_for_item", return_value={}):
            assert _item_source_language({"id": 1}, settings) == "en"

    def test_global_source_when_the_profile_cannot_be_read(self):
        from wanted_search.process import _item_source_language

        settings = MagicMock(source_language="en")
        with patch(
            "services.mt_provisional._resolve_profile_for_item",
            side_effect=RuntimeError("db down"),
        ):
            assert _item_source_language({"id": 1}, settings) == "en"


class TestSeriesDetailSource:
    def test_series_detail_shows_the_profile_source(self):
        from routes.library.series import _profile_source

        settings = MagicMock(source_language="en", source_language_name="English")
        profile = {"source_language": "de", "source_language_name": "German"}
        assert _profile_source(profile, settings) == ("de", "German")

    def test_series_detail_falls_back_to_the_global_source(self):
        from routes.library.series import _profile_source

        settings = MagicMock(source_language="en", source_language_name="English")
        assert _profile_source(None, settings) == ("en", "English")
        assert _profile_source({"source_language": ""}, settings) == ("en", "English")
