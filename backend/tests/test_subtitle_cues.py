"""Tests for the shared subtitle cue loader + density statistics."""


def test_cue_statistics_dense_vs_sparse():
    from services.subtitle_cues import Cue, cue_statistics

    # 60 cues over 1 minute -> dense dialogue
    dense = [Cue(i * 1000, i * 1000 + 800, "hello there") for i in range(60)]
    density, cps, _overlap = cue_statistics(dense)
    assert density > 3.0
    assert cps > 0

    # 2 cues over 10 minutes -> sparse (signs)
    sparse = [Cue(0, 2000, "SHOP"), Cue(600_000, 602_000, "EXIT")]
    sdensity, _c, _o = cue_statistics(sparse)
    assert sdensity <= 3.0


def test_cue_statistics_empty():
    from services.subtitle_cues import cue_statistics

    assert cue_statistics([]) == (0.0, 0.0, 0.0)


def test_load_cues_parses_srt(tmp_path):
    from services.subtitle_cues import load_cues

    srt = tmp_path / "x.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n00:00:03,000 --> 00:00:04,000\nWorld\n",
        encoding="utf-8",
    )
    cues = load_cues(str(srt))
    assert len(cues) == 2
    assert cues[0].text.strip() == "Hello"
