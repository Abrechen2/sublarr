"""The file a provider takes out of an archive must be the queried episode too.

VM 191 (RC 1.17.0-rc.1): a listing ``Synthetic.S02E05.zip`` passed the episode
gate, the archive's one member was ``Synthetic.S01E05.srt``, and that member
was saved for S02E05. The gate before download only sees the listing; the
member name is checked once the provider has picked it.
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.episode_gate import archive_member_reason

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


def _query(**kwargs) -> VideoQuery:
    return VideoQuery(season=2, episode=5, languages=["de"], sonarr_absolute_episode=17, **kwargs)


def _result(sid: str, listed: str, member: str | None, matches=("series", "episode")):
    result = SubtitleResult(
        provider_name="customapi",
        subtitle_id=sid,
        language="de",
        format=SubtitleFormat.SRT,
        filename=listed,
        matches=set(matches),
    )
    result._member = member  # what the fake download picks out of the archive
    return result


def _download(result):
    if result._member is not None:
        result.filename = result._member
    return SRT


def _run(results, query):
    from providers.download_manager import search_and_download_best

    with patch("providers.download_manager.decision_log") as dlog:
        best = search_and_download_best(
            search_fn=lambda *_a, **_kw: results,
            download_fn=_download,
            update_stats_fn=MagicMock(),
            query=query,
        )
    return best, [c.args[2] for c in dlog.download_attempt.call_args_list]


class TestArchiveMemberReason:
    def test_member_of_another_season(self):
        reason = archive_member_reason(
            _result("a", "Synthetic.S02E05.zip", None), "Synthetic.S01E05.srt", _query()
        )
        assert "S01E05" in reason and "archive member" in reason

    def test_member_of_the_queried_episode(self):
        result = _result("a", "Pack.S02.zip", None)
        assert archive_member_reason(result, "Synthetic.S02E05.srt", _query()) == ""

    def test_member_without_numbering_is_left_to_the_listing(self):
        result = _result("a", "Synthetic.S02E05.zip", None)
        assert archive_member_reason(result, "german.srt", _query()) == ""

    def test_absolute_numbered_member_is_the_queried_episode(self):
        result = _result("a", "Synthetic.S02E05.zip", None)
        assert archive_member_reason(result, "[Group] Synthetic - 17.ass", _query()) == ""

    def test_a_hash_match_is_trusted(self):
        result = _result("a", "Synthetic.S02E05.zip", None, matches=("hash",))
        assert archive_member_reason(result, "Synthetic.S01E05.srt", _query()) == ""

    def test_movies_are_not_checked(self):
        result = _result("a", "Film.zip", None)
        assert archive_member_reason(result, "Film.S01E05.srt", VideoQuery(title="Film")) == ""


class TestDownloadLoop:
    def test_contradicting_member_falls_through_to_the_next_result(self):
        wrong = _result("archive", "Synthetic.S02E05.zip", "Synthetic.S01E05.srt")
        right = _result("plain", "Synthetic.S02E05.srt", None)

        best, statuses = _run([wrong, right], _query())

        assert best is right
        assert statuses == ["episode_mismatch", "selected"]

    def test_only_contradicting_member_gives_no_result(self):
        wrong = _result("archive", "Synthetic.S02E05.zip", "Synthetic.S01E05.srt")
        assert _run([wrong], _query())[0] is None

    def test_matching_member_is_kept(self):
        good = _result("archive", "Synthetic.S02.zip", "Synthetic.S02E05.srt")
        assert _run([good], _query())[0] is good


class TestCustomApiNamesTheMember:
    def test_the_extracted_member_becomes_the_result_filename(self):
        from providers.customapi import CustomApiProvider

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("Synthetic.S01E05.srt", SRT)
        provider = CustomApiProvider(base_url="http://provider.invalid")
        provider.session = MagicMock()
        result = _result("archive", "Synthetic.S02E05.zip", None)
        result.download_url = "http://provider.invalid/download/archive"

        with (
            patch("providers.customapi.validate_download_url", return_value=(True, "")),
            patch("providers.customapi._stream_download", return_value=buf.getvalue()),
        ):
            content = provider.download(result)

        assert content == SRT
        assert result.filename == "Synthetic.S01E05.srt"
