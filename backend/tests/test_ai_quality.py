"""Tests for the advisory AI subtitle-quality verdict (services.ai_quality)."""

import json
from pathlib import Path

import pytest

import services.ai_quality as aq

# ---- Cue sampling ---------------------------------------------------------------


def _write_srt(path: Path, lines: list[str]) -> str:
    blocks = []
    for i, text in enumerate(lines, start=1):
        start = f"00:00:{i:02d},000"
        end = f"00:00:{i:02d},900"
        blocks.append(f"{i}\n{start} --> {end}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return str(path)


def test_sample_cues_dedupes_and_skips_short(tmp_path):
    path = _write_srt(
        tmp_path / "a.de.srt",
        ["Hallo Welt!", "Hallo Welt!", "OK", "Wie geht es dir heute?"],
    )
    cues = aq.sample_cues(path, 30)
    # duplicate removed, "OK" (<3 chars) removed
    assert cues == ["Hallo Welt!", "Wie geht es dir heute?"]


def test_sample_cues_caps_and_spreads(tmp_path):
    path = _write_srt(tmp_path / "a.de.srt", [f"Zeile Nummer {i} im Test" for i in range(50)])
    cues = aq.sample_cues(path, 10)
    assert len(cues) == 10
    # even spread: first sample is from the start, samples strictly ordered
    assert cues[0] == "Zeile Nummer 0 im Test"
    indexes = [int(c.split()[2]) for c in cues]
    assert indexes == sorted(indexes)


def test_sample_cues_truncates_long_lines(tmp_path):
    path = _write_srt(tmp_path / "a.de.srt", ["x" * 500, "kurze Zeile hier"])
    cues = aq.sample_cues(path, 30)
    assert max(len(c) for c in cues) <= aq._MAX_CUE_CHARS


# ---- Deterministic scoring pieces -----------------------------------------------


def test_encoding_damage_thresholds():
    clean = ["Alles gut hier"] * 10
    assert aq._measure_encoding_damage(clean) == 0
    one_bad = clean[:9] + ["kaputt � hier"]
    assert aq._measure_encoding_damage(one_bad) == 1
    two_bad = clean[:8] + ["kaputt � hier", "Ã¤rgerlich"]
    assert aq._measure_encoding_damage(two_bad) == 2
    mostly_bad = ["â€œZitatâ€\x9d"] * 4 + clean[:6]
    assert aq._measure_encoding_damage(mostly_bad) == 3
    assert aq._measure_encoding_damage([]) == 0


def test_clamp_scores_tolerates_garbage():
    scores = aq._clamp_scores(
        {"machine_translation": "7", "ocr_artifacts": None, "grammar": -2}, encoding_damage=1
    )
    assert scores == {
        "machine_translation": 3,
        "ocr_artifacts": 0,
        "grammar": 0,
        "encoding_damage": 1,
    }


@pytest.mark.parametrize(
    "scores,expected",
    [
        ({"machine_translation": 0, "ocr_artifacts": 0, "grammar": 0, "encoding_damage": 0}, "green"),
        ({"machine_translation": 1, "ocr_artifacts": 1, "grammar": 0, "encoding_damage": 0}, "green"),
        ({"machine_translation": 2, "ocr_artifacts": 0, "grammar": 0, "encoding_damage": 0}, "yellow"),
        ({"machine_translation": 1, "ocr_artifacts": 1, "grammar": 1, "encoding_damage": 0}, "yellow"),
        ({"machine_translation": 3, "ocr_artifacts": 0, "grammar": 0, "encoding_damage": 0}, "red"),
        ({"machine_translation": 2, "ocr_artifacts": 2, "grammar": 2, "encoding_damage": 0}, "red"),
    ],
)
def test_derive_verdict(scores, expected):
    assert aq._derive_verdict(scores) == expected


def test_clean_reasons_caps_and_filters():
    raw = ["  gut  ", 42, None, "x" * 500, "a", "b", "c", "d"]
    reasons = aq._clean_reasons(raw)
    assert len(reasons) == aq._MAX_REASONS
    assert reasons[0] == "gut"
    assert all(len(r) <= aq._MAX_REASON_CHARS for r in reasons)
    assert aq._clean_reasons("not a list") == []


def test_parse_verdict_json_tolerates_prose():
    parsed = aq._parse_verdict_json('Sure! {"grammar": 2, "reasons": ["x"]} hope that helps')
    assert parsed["grammar"] == 2
    with pytest.raises(ValueError):
        aq._parse_verdict_json("no json here")


# ---- analyze_file with mocked LLM ------------------------------------------------


def test_analyze_file_success(tmp_path, monkeypatch):
    path = _write_srt(tmp_path / "a.de.srt", [f"Ein ganz normaler Satz {i}" for i in range(10)])
    monkeypatch.setattr(
        aq,
        "_call_ollama",
        lambda cues, language, settings: (
            {"machine_translation": 2, "ocr_artifacts": 0, "grammar": 1, "reasons": ["klingt wörtlich"]},
            "test-model",
        ),
    )
    result = aq.analyze_file(path, "de")
    assert result is not None
    assert result["verdict"] == "yellow"
    assert result["scores"]["machine_translation"] == 2
    assert result["reasons"] == ["klingt wörtlich"]
    assert result["model"] == "test-model"
    assert result["sampled_cues"] == 10


def test_analyze_file_too_few_cues_returns_none(tmp_path, monkeypatch):
    path = _write_srt(tmp_path / "a.de.srt", ["Nur ein Satz hier"])
    called = []
    monkeypatch.setattr(aq, "_call_ollama", lambda *a: called.append(1))
    assert aq.analyze_file(path, "de") is None
    assert not called


def test_analyze_file_llm_error_returns_none(tmp_path, monkeypatch):
    path = _write_srt(tmp_path / "a.de.srt", [f"Ein ganz normaler Satz {i}" for i in range(10)])

    def _boom(cues, language, settings):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(aq, "_call_ollama", _boom)
    assert aq.analyze_file(path, "de") is None


def test_analyze_file_missing_file_returns_none():
    assert aq.analyze_file("/nonexistent/x.de.srt", "de") is None


# ---- Persistence roundtrip -------------------------------------------------------


def test_save_get_batch_delete_roundtrip(app_ctx):
    from db.quality import (
        delete_ai_quality_result,
        get_ai_quality_result,
        get_ai_quality_results_for_paths,
        save_ai_quality_result,
    )

    saved = save_ai_quality_result(
        "/media/a/ep1.de.ass", "de", "yellow", '{"grammar": 2}', '["x"]', "m", 30
    )
    assert saved["verdict"] == "yellow"

    # replace-on-save: second save for the same path leaves exactly one row
    save_ai_quality_result("/media/a/ep1.de.ass", "de", "green", "{}", "[]", "m", 30)
    row = get_ai_quality_result("/media/a/ep1.de.ass")
    assert row["verdict"] == "green"

    save_ai_quality_result("/media/a/ep2.de.ass", "de", "red", "{}", "[]", "m", 12)
    batch = get_ai_quality_results_for_paths(
        ["/media/a/ep1.de.ass", "/media/a/ep2.de.ass", "/media/a/missing.de.ass"]
    )
    assert set(batch.keys()) == {"/media/a/ep1.de.ass", "/media/a/ep2.de.ass"}

    assert delete_ai_quality_result("/media/a/ep1.de.ass") == 1
    assert get_ai_quality_result("/media/a/ep1.de.ass") is None
    assert get_ai_quality_results_for_paths([]) == {}


def test_attach_ai_quality(app_ctx):
    from db.quality import save_ai_quality_result

    save_ai_quality_result(
        "/media/a/ep1.de.ass",
        "de",
        "red",
        json.dumps({"machine_translation": 3}),
        json.dumps(["MTL"]),
        "m",
        30,
    )
    entries = [
        {"file_path": "/media/a/ep1.mkv", "language": "de", "format": "ass"},
        {"file_path": "/media/a/ep2.mkv", "language": "de", "format": "srt"},
        {"file_path": "", "language": "", "format": ""},
    ]
    aq.attach_ai_quality(entries)
    assert entries[0]["ai_quality"]["verdict"] == "red"
    assert entries[0]["ai_quality"]["scores"] == {"machine_translation": 3}
    assert entries[0]["ai_quality"]["reasons"] == ["MTL"]
    assert entries[1]["ai_quality"] is None
    assert entries[2]["ai_quality"] is None


# ---- maybe_queue_analysis guardrails ---------------------------------------------


def test_maybe_queue_analysis_disabled_is_noop(app_ctx, monkeypatch):
    submitted = []
    monkeypatch.setattr("services.background_tasks.submit_background", submitted.append)
    aq.maybe_queue_analysis("/media/a/ep1.mkv", "de", "ass")
    assert not submitted


def test_maybe_queue_analysis_never_raises_without_context():
    # No app context, no settings guarantees — must still be silent.
    aq.maybe_queue_analysis("", "", "")


# ---- Routes ---------------------------------------------------------------------


def test_route_get_requires_path(client):
    resp = client.get("/api/v1/quality/ai")
    assert resp.status_code == 400


def test_route_get_rejects_outside_media(client):
    resp = client.get("/api/v1/quality/ai?path=/etc/passwd")
    assert resp.status_code == 403


def test_route_get_returns_null_then_result(client, tmp_path):
    target = str(tmp_path / "ep1.de.ass")
    resp = client.get(f"/api/v1/quality/ai?path={target}")
    assert resp.status_code == 200
    assert resp.get_json()["result"] is None

    from db.quality import save_ai_quality_result

    save_ai_quality_result(target, "de", "yellow", '{"grammar": 2}', '["x"]', "m", 30)
    resp = client.get(f"/api/v1/quality/ai?path={target}")
    body = resp.get_json()["result"]
    assert body["verdict"] == "yellow"
    assert body["scores"] == {"grammar": 2}


def test_route_analyze_disabled_returns_503(client, tmp_path):
    resp = client.post(
        "/api/v1/quality/ai/analyze", json={"path": str(tmp_path / "a.de.srt"), "language": "de"}
    )
    assert resp.status_code == 503


def test_route_analyze_enabled_flow(client, tmp_path, monkeypatch):
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ai_quality_enabled", True, raising=False)

    resp = client.post("/api/v1/quality/ai/analyze", json={})
    assert resp.status_code == 400

    resp = client.post("/api/v1/quality/ai/analyze", json={"path": "/etc/passwd"})
    assert resp.status_code == 403

    missing = str(tmp_path / "missing.de.srt")
    resp = client.post("/api/v1/quality/ai/analyze", json={"path": missing, "language": "de"})
    assert resp.status_code == 404

    real = _write_srt(tmp_path / "real.de.srt", [f"Ein Satz {i} zum Testen" for i in range(6)])
    ran = []
    monkeypatch.setattr(
        "services.background_tasks.submit_background", lambda fn, *a, **kw: ran.append(fn)
    )
    resp = client.post("/api/v1/quality/ai/analyze", json={"path": real, "language": "de"})
    assert resp.status_code == 202
    assert len(ran) == 1
