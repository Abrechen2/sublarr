"""HTTP tests for routes/subtitles/combine.py — combined/bilingual subtitle
endpoints (V1.6 Feature #1, C3).

  POST /api/v1/library/episodes/<ep_id>/subtitles/combine
  POST /api/v1/library/movies/<movie_id>/subtitles/combine
  POST /api/v1/library/subtitles/combine-batch

Runs with the real app/client fixture so the managed subtitle_downloads row
(source="combined") can be verified.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pysubs2

_SRT_DE = [(1000, 3000, "Hallo Welt")]
_SRT_EN = [(1000, 3000, "Hello world")]


def _write_sidecar(directory, stem, lang, cues, fmt="srt"):
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        ev = pysubs2.SSAEvent(start=start, end=end)
        ev.plaintext = text
        subs.events.append(ev)
    path = os.path.join(directory, f"{stem}.{lang}.{fmt}")
    subs.save(path, format_=fmt)
    return path


def _mock_episode(monkeypatch, video_path):
    client = MagicMock()
    client.get_episode_file_path.return_value = video_path
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: client)
    monkeypatch.setattr("config.map_path", lambda p: p)
    return client


def _combine(client, url, **body):
    return client.post(url, json=body)


# ── episode combine ─────────────────────────────────────────────────────────


def test_combine_episode_success_records_combined_source(client, temp_dir, monkeypatch):
    from db.models.providers import SubtitleDownload

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "episode", "de", _SRT_DE)
    _write_sidecar(temp_dir, "episode", "en", _SRT_EN)
    _mock_episode(monkeypatch, video)

    resp = _combine(
        client,
        "/api/v1/library/episodes/1/subtitles/combine",
        languages=["de", "en"],
        format="srt",
    )
    data = resp.get_json()
    assert resp.status_code == 201, data
    out = data["combined_path"]
    assert out.endswith(".de-en.combined.srt")
    assert os.path.exists(out)

    result = pysubs2.SSAFile.load(out)
    joined = result.events[0].plaintext
    assert "Hallo Welt" in joined and "Hello world" in joined

    with client.application.app_context():
        # file_path is the VIDEO path, matching every other source -- see
        # test_subtitle_download_file_path_convention.py.
        row = SubtitleDownload.query.filter_by(file_path=video).one()
        assert row.source == "combined"
        assert row.format == "srt"


def test_combine_episode_ass_positions(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "ep2.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep2", "de", _SRT_DE, fmt="ass")
    _write_sidecar(temp_dir, "ep2", "en", _SRT_EN, fmt="ass")
    _mock_episode(monkeypatch, video)

    resp = _combine(
        client,
        "/api/v1/library/episodes/1/subtitles/combine",
        languages=["de", "en"],
        format="ass",
    )
    assert resp.status_code == 201
    result = pysubs2.SSAFile.load(resp.get_json()["combined_path"])
    de = next(e for e in result.events if "Hallo Welt" in e.text)
    en = next(e for e in result.events if "Hello world" in e.text)
    assert "\\an2" in de.text  # primary bottom
    assert "\\an8" in en.text  # secondary top


def test_combine_episode_missing_language_422(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "ep3.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "ep3", "de", _SRT_DE)  # only DE present
    _mock_episode(monkeypatch, video)

    resp = _combine(
        client,
        "/api/v1/library/episodes/1/subtitles/combine",
        languages=["de", "en"],
        format="srt",
    )
    assert resp.status_code == 422
    assert "en" in resp.get_json()["error"]
    assert not os.path.exists(os.path.join(temp_dir, "ep3.de-en.combined.srt"))


def test_combine_invalid_format_400(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "ep4.mkv")
    Path(video).touch()
    _mock_episode(monkeypatch, video)
    resp = _combine(
        client,
        "/api/v1/library/episodes/1/subtitles/combine",
        languages=["de", "en"],
        format="vtt",
    )
    assert resp.status_code == 400


def test_combine_too_few_languages_400(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "ep5.mkv")
    Path(video).touch()
    _mock_episode(monkeypatch, video)
    resp = _combine(
        client, "/api/v1/library/episodes/1/subtitles/combine", languages=["de"], format="srt"
    )
    assert resp.status_code == 400


# ── movie combine ───────────────────────────────────────────────────────────


def test_combine_movie_success(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "movie.mkv")
    Path(video).touch()
    _write_sidecar(temp_dir, "movie", "de", _SRT_DE)
    _write_sidecar(temp_dir, "movie", "en", _SRT_EN)
    monkeypatch.setattr("db.standalone.get_standalone_movies", lambda mid: {"file_path": video})

    resp = _combine(
        client,
        "/api/v1/library/movies/7/subtitles/combine",
        languages=["de", "en"],
        format="srt",
    )
    assert resp.status_code == 201, resp.get_json()
    assert os.path.exists(resp.get_json()["combined_path"])


# ── batch combine ───────────────────────────────────────────────────────────


def test_combine_batch_reports_combined_and_skipped(client, temp_dir, monkeypatch):
    # ep 1 has both languages → combined; ep 2 only DE → skipped
    v1 = os.path.join(temp_dir, "b1.mkv")
    v2 = os.path.join(temp_dir, "b2.mkv")
    Path(v1).touch()
    Path(v2).touch()
    _write_sidecar(temp_dir, "b1", "de", _SRT_DE)
    _write_sidecar(temp_dir, "b1", "en", _SRT_EN)
    _write_sidecar(temp_dir, "b2", "de", _SRT_DE)

    paths = {1: v1, 2: v2}
    sonarr = MagicMock()
    sonarr.get_episode_file_path.side_effect = lambda eid: paths.get(eid)
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    resp = client.post(
        "/api/v1/library/subtitles/combine-batch",
        json={"episode_ids": [1, 2], "languages": ["de", "en"], "format": "srt"},
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["combined"] == 1
    assert data["skipped"] == 1
    statuses = {r["id"]: r["status"] for r in data["results"]}
    assert statuses == {1: "combined", 2: "skipped"}
