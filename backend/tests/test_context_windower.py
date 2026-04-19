"""ContextWindower tests — chunking subtitles with lookback/lookahead."""

import pytest


def test_single_batch_no_splits():
    from translation.context_windower import build_chunks

    lines = ["a", "b", "c"]
    chunks = build_chunks(lines, batch_size=10, lookback=5, lookahead=3)
    assert len(chunks) == 1
    assert chunks[0].batch == ["a", "b", "c"]
    assert chunks[0].lookback == []
    assert chunks[0].lookahead == []
    assert chunks[0].batch_start_index == 0


def test_two_batches_exact_fit():
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(20)]  # 20 lines
    chunks = build_chunks(lines, batch_size=10, lookback=3, lookahead=2)
    assert len(chunks) == 2
    # First chunk: no lookback, 2-line lookahead
    assert chunks[0].batch == [f"line{i}" for i in range(10)]
    assert chunks[0].lookback == []
    assert chunks[0].lookahead == ["line10", "line11"]
    assert chunks[0].batch_start_index == 0
    # Second chunk: 3-line lookback, no lookahead
    assert chunks[1].batch == [f"line{i}" for i in range(10, 20)]
    assert chunks[1].lookback == ["line7", "line8", "line9"]
    assert chunks[1].lookahead == []
    assert chunks[1].batch_start_index == 10


def test_mid_file_chunk_has_both():
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(30)]  # 30 lines, 3 batches of 10
    chunks = build_chunks(lines, batch_size=10, lookback=3, lookahead=2)
    assert len(chunks) == 3
    mid = chunks[1]
    assert mid.batch == [f"line{i}" for i in range(10, 20)]
    assert mid.lookback == ["line7", "line8", "line9"]
    assert mid.lookahead == ["line20", "line21"]
    assert mid.batch_start_index == 10


def test_lookback_clipped_to_available():
    """If lookback > available preceding lines, clip to what's there."""
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(20)]
    chunks = build_chunks(lines, batch_size=10, lookback=100, lookahead=2)
    # First chunk: lookback is empty (no preceding lines)
    assert chunks[0].lookback == []
    # Second chunk: lookback clipped to 10 available
    assert chunks[1].lookback == [f"line{i}" for i in range(10)]


def test_lookahead_clipped_to_available():
    """If lookahead > available trailing lines, clip."""
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(20)]
    chunks = build_chunks(lines, batch_size=10, lookback=3, lookahead=100)
    # First chunk: lookahead clipped to 10 available trailing
    assert chunks[0].lookahead == [f"line{i}" for i in range(10, 20)]
    # Second chunk: no lookahead
    assert chunks[1].lookahead == []


def test_zero_lookback_allowed():
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(20)]
    chunks = build_chunks(lines, batch_size=10, lookback=0, lookahead=5)
    assert chunks[1].lookback == []
    assert len(chunks[0].lookahead) == 5


def test_zero_lookahead_allowed():
    from translation.context_windower import build_chunks

    lines = [f"line{i}" for i in range(20)]
    chunks = build_chunks(lines, batch_size=10, lookback=3, lookahead=0)
    assert chunks[0].lookahead == []


def test_empty_file_returns_empty_list():
    from translation.context_windower import build_chunks

    chunks = build_chunks([], batch_size=10, lookback=3, lookahead=2)
    assert chunks == []


def test_single_line_file():
    from translation.context_windower import build_chunks

    chunks = build_chunks(["only"], batch_size=10, lookback=3, lookahead=2)
    assert len(chunks) == 1
    assert chunks[0].batch == ["only"]


def test_batch_size_larger_than_file():
    from translation.context_windower import build_chunks

    lines = ["a", "b", "c"]
    chunks = build_chunks(lines, batch_size=100, lookback=5, lookahead=5)
    assert len(chunks) == 1
    assert chunks[0].batch == ["a", "b", "c"]


def test_negative_lookback_raises():
    from translation.context_windower import build_chunks

    with pytest.raises(ValueError, match="lookback"):
        build_chunks(["a"], batch_size=10, lookback=-1, lookahead=0)


def test_zero_batch_size_raises():
    from translation.context_windower import build_chunks

    with pytest.raises(ValueError, match="batch_size"):
        build_chunks(["a"], batch_size=0, lookback=0, lookahead=0)
