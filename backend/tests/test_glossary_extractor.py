from services.glossary_extractor import _classify_term, extract_candidates


def test_extract_candidates_basic(tmp_path):
    srt = tmp_path / "ep01.en.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nNaruto arrives at Konoha.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nNaruto smiles.\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\nNaruto runs to Konoha.\n",
        encoding="utf-8",
    )
    candidates = extract_candidates(str(tmp_path), source_lang="en", min_freq=2)
    terms = [c["source_term"] for c in candidates]
    assert "Naruto" in terms
    assert "Konoha" in terms


def test_extract_candidates_min_freq_filter(tmp_path):
    srt = tmp_path / "ep01.en.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nOnce Naruto appeared.\n",
        encoding="utf-8",
    )
    candidates = extract_candidates(str(tmp_path), source_lang="en", min_freq=3)
    assert candidates == []


def test_classify_term_character():
    assert _classify_term("Naruto") == "character"


def test_classify_term_place():
    assert _classify_term("Konoha Village") == "place"


def test_extract_candidates_no_files(tmp_path):
    candidates = extract_candidates(str(tmp_path), source_lang="en", min_freq=2)
    assert candidates == []


def test_extract_candidates_invalid_dir():
    candidates = extract_candidates("/nonexistent/path", source_lang="en", min_freq=2)
    assert candidates == []


def test_candidate_has_required_fields(tmp_path):
    srt = tmp_path / "ep01.en.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nNaruto speaks.\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nNaruto runs.\n\n"
        "3\n00:00:05,000 --> 00:00:07,000\nNaruto jumps.\n",
        encoding="utf-8",
    )
    candidates = extract_candidates(str(tmp_path), source_lang="en", min_freq=2)
    assert len(candidates) >= 1
    c = candidates[0]
    assert "source_term" in c
    assert "term_type" in c
    assert "frequency" in c
    assert "confidence" in c
    assert 0 < c["confidence"] <= 1
