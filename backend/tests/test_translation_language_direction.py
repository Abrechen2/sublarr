"""A translation is asked for in the direction the caller requested.

Prod 2026-09-16: every Ollama request carried "from English to German" —
the global source/target — whatever the call asked for. A German subtitle
sent for an English target came back as reworded German and was saved as
``.en.srt`` (39 of 40 sampled EN machine translations were German) and 70 049
German lines were cached in translation memory under de->en.

Also covered: a machine translation is never itself used as a translation
source (owner decision 2026-09-16 — a translation of a translation is not a
source, the German sidecar feeding those EN files was often an MT itself).
"""

import pytest

# ── Prompt direction ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("src", "tgt", "expected"),
    [
        ("de", "en", "from German to English"),
        ("ja", "de", "from Japanese to German"),
        ("en", "de", "from English to German"),
    ],
)
def test_user_prompt_names_the_requested_direction(app_ctx, src, tgt, expected):
    from translation.llm_utils import build_translation_prompt

    prompt = build_translation_prompt(["Silvesterabend."], src, tgt)

    assert expected in prompt
    if (src, tgt) != ("en", "de"):
        assert "from English to German" not in prompt


def test_prompt_preset_placeholders_follow_the_request(app_ctx, monkeypatch):
    monkeypatch.setattr(
        "db.translation.get_default_prompt_preset",
        lambda: {"prompt_template": "Render {source_language} as {target_language}:\n"},
    )
    from translation.llm_utils import build_translation_prompt

    prompt = build_translation_prompt(["Hallo"], "de", "en")

    assert "Render German as English" in prompt


def test_global_template_is_unchanged_without_a_direction(app_ctx):
    """The config hash and settings UI read the template without a direction."""
    from config import get_settings

    assert "from English to German" in get_settings().get_prompt_template()


def _make_backend(system_prompt: str = ""):
    from translation.ollama import OllamaBackend

    backend = OllamaBackend.__new__(OllamaBackend)
    backend.config = {"use_chat_api": "true", "system_prompt": system_prompt}
    return backend


def test_default_system_prompt_for_german_target_is_unchanged():
    """The German system prompt is what the fine-tunes were trained on."""
    prompt = _make_backend()._build_system_prompt(None, source_lang="en", target_lang="de")

    assert "ins Deutsche" in prompt


def test_default_system_prompt_names_a_non_german_target():
    prompt = _make_backend()._build_system_prompt(None, source_lang="de", target_lang="en")

    assert "ins Deutsche" not in prompt
    assert "German" in prompt and "English" in prompt


def test_chat_messages_carry_the_requested_direction(app_ctx):
    messages = _make_backend()._assemble_messages(["Hallo"], "de", "en", None)

    system = next(m["content"] for m in messages if m["role"] == "system")
    user = next(m["content"] for m in messages if m["role"] == "user")
    assert "ins Deutsche" not in system
    assert "from German to English" in user


# ── A machine translation is never a translation source ─────────────────────


def _record_mt(video: str, lang: str, fmt: str) -> None:
    from db.providers import record_subtitle_download

    record_subtitle_download(
        "translation",
        f"mt:x.{lang}.{fmt}",
        lang,
        fmt,
        video,
        0,
        source="machine_translation",
        record_stats=False,
    )


def test_machine_translated_sidecar_is_not_a_source(app_ctx, tmp_path):
    from translator._helpers import find_any_source_sub

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    (tmp_path / "ep.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nMT\n")
    _record_mt(str(mkv), "de", "srt")

    assert find_any_source_sub(str(mkv), target_language="en") == (None, None)


def test_genuine_sidecar_in_same_language_is_still_used(app_ctx, tmp_path):
    from translator._helpers import find_any_source_sub

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    (tmp_path / "ep.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nMT\n")
    genuine = tmp_path / "ep.ger.srt"
    genuine.write_text("1\n00:00:01,000 --> 00:00:02,000\nEcht\n")
    _record_mt(str(mkv), "de", "srt")

    path, lang = find_any_source_sub(str(mkv), target_language="en")

    assert (path, lang) == (str(genuine), "de")


def test_sidecar_without_translation_record_is_a_source(app_ctx, tmp_path):
    from translator._helpers import find_any_source_sub

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    en = tmp_path / "ep.en.srt"
    en.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")

    assert find_any_source_sub(str(mkv), target_language="de") == (str(en), "en")


# ── Provenance is the latest record, not any record (Codex review) ──────────


def _record_provider(video: str, lang: str, fmt: str) -> None:
    from db.providers import record_subtitle_download

    record_subtitle_download(
        "animetosho",
        f"real:{lang}.{fmt}",
        lang,
        fmt,
        video,
        250,
        source="provider",
        record_stats=False,
    )


def test_genuine_subtitle_that_replaced_a_machine_translation_is_a_source(app_ctx, tmp_path):
    """Same path, same format: the provider download is newer than the MT row."""
    import time

    from translator._helpers import find_any_source_sub

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    de = tmp_path / "ep.de.srt"
    de.write_text("1\n00:00:01,000 --> 00:00:02,000\nEcht\n")
    _record_mt(str(mkv), "de", "srt")
    time.sleep(0.01)
    _record_provider(str(mkv), "de", "srt")

    assert find_any_source_sub(str(mkv), target_language="en") == (str(de), "de")


def test_machine_translation_newer_than_a_download_is_still_excluded(app_ctx, tmp_path):
    import time

    from translator._helpers import find_any_source_sub

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    (tmp_path / "ep.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nMT\n")
    _record_provider(str(mkv), "de", "srt")
    time.sleep(0.01)
    _record_mt(str(mkv), "de", "srt")

    assert find_any_source_sub(str(mkv), target_language="en") == (None, None)


def test_listing_skips_superseded_machine_translations(app_ctx, tmp_path):
    import time

    from db.providers import list_machine_translations

    mkv = str(tmp_path / "ep.mkv")
    _record_mt(mkv, "de", "srt")
    _record_mt(mkv, "en", "srt")
    time.sleep(0.01)
    _record_provider(mkv, "de", "srt")

    assert sorted(list_machine_translations()) == [(mkv, "en", "srt")]
