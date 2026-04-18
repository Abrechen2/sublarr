"""Regression: duplicate-group scanner flags cross-episode groups.

When two subtitle files share identical content but belong to different
episodes (SxxEyy codes), the dedup scanner must mark the group with
``cross_episode=True`` so the UI can warn the user — deleting one
typically leaves the *wrong* subtitle file behind.
"""

from __future__ import annotations

from datetime import UTC, datetime

from db.models.cleanup import SubtitleHash
from db.repositories.cleanup import CleanupRepository
from extensions import db


def _seed(file_path: str, content_hash: str):
    row = SubtitleHash(
        file_path=file_path,
        content_hash=content_hash,
        file_size=1024,
        format="srt",
        language="de",
        line_count=100,
        last_scanned=datetime.now(UTC),
    )
    db.session.add(row)
    db.session.commit()
    return row


class TestCrossEpisodeFlag:
    HASH_A = "a" * 64
    HASH_B = "b" * 64

    def test_same_episode_different_language_not_cross(self, app_ctx):
        """A group whose files share SxxEyy (e.g. de + en for same episode)
        is not cross-episode — the user is free to dedup."""
        _seed("/m/Show/S1/Show - S01E10 - Title.de.srt", self.HASH_A)
        _seed("/m/Show/S1/Show - S01E10 - Title.en.srt", self.HASH_A)
        groups = CleanupRepository().get_duplicate_groups()
        assert len(groups) == 1
        assert groups[0]["cross_episode"] is False

    def test_different_seasons_are_cross(self, app_ctx):
        """S01E10 vs S02E10 with identical content is the classic misfile."""
        _seed("/m/Show/S1/Show - S01E10 - Title A.de.srt", self.HASH_A)
        _seed("/m/Show/S2/Show - S02E10 - Title B.de.srt", self.HASH_A)
        groups = CleanupRepository().get_duplicate_groups()
        assert len(groups) == 1
        assert groups[0]["cross_episode"] is True

    def test_different_episodes_same_season_are_cross(self, app_ctx):
        _seed("/m/Show/S1/Show - S01E10.de.srt", self.HASH_A)
        _seed("/m/Show/S1/Show - S01E11.de.srt", self.HASH_A)
        groups = CleanupRepository().get_duplicate_groups()
        assert groups[0]["cross_episode"] is True

    def test_file_without_episode_code_alone_not_cross(self, app_ctx):
        """Two movies with no SxxEyy code — absence of codes alone is safe."""
        _seed("/m/Movies/Film 1.de.srt", self.HASH_A)
        _seed("/m/Movies/Film 1 (copy).de.srt", self.HASH_A)
        groups = CleanupRepository().get_duplicate_groups()
        assert groups[0]["cross_episode"] is False

    def test_mixed_episode_and_no_code_is_cross(self, app_ctx):
        """Some files have episode codes, others don't — suspicious,
        warn the user."""
        _seed("/m/Show/S01E10.de.srt", self.HASH_A)
        _seed("/m/Movies/Unknown.de.srt", self.HASH_A)
        groups = CleanupRepository().get_duplicate_groups()
        assert groups[0]["cross_episode"] is True

    def test_only_returns_groups_with_duplicates(self, app_ctx):
        """Single-file "groups" are not returned — unchanged behaviour."""
        _seed("/m/Show/S01E10.de.srt", self.HASH_A)
        _seed("/m/Show/S01E11.de.srt", self.HASH_B)  # distinct hash → no group
        groups = CleanupRepository().get_duplicate_groups()
        assert groups == []
