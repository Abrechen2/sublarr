"""The library filters get real data (#50).

"Anime" matched almost every series (title, continuing, seasons > 0) and
"Low score" measured video-file coverage instead of subtitle scores. The
library payload now carries is_anime (Sonarr's own classification) and
low_score_count (upgrade candidates, the dashboard's definition).
"""

from __future__ import annotations

from datetime import UTC, datetime


def test_is_anime_follows_sonarr_type_genre_and_tag():
    from sonarr_client import is_anime_series

    assert is_anime_series({"seriesType": "anime"}, set())
    assert is_anime_series({"seriesType": "standard", "genres": ["Anime"]}, set())
    assert is_anime_series({"seriesType": "standard", "tags": [7]}, {7})
    assert not is_anime_series(
        {"title": "Live Action Anime Club", "seriesType": "standard", "status": "continuing"},
        set(),
    )


def test_low_score_counts_per_series(app_ctx):
    from db.models.core import WantedItem
    from db.repositories.wanted import WantedRepository
    from extensions import db

    def item(path, sid, upgrade, status="wanted"):
        return WantedItem(
            item_type="episode",
            file_path=path,
            sonarr_series_id=sid,
            target_language="de",
            status=status,
            upgrade_candidate=upgrade,
            added_at=datetime(2026, 11, 25, tzinfo=UTC),
            updated_at=datetime(2026, 11, 25, tzinfo=UTC),
        )

    db.session.add_all(
        [
            item("/a/1.mkv", 1, 1),
            item("/a/2.mkv", 1, 1),
            item("/a/3.mkv", 1, 0),
            item("/a/4.mkv", 1, 1, status="ignored"),
            item("/b/1.mkv", 2, 0),
        ]
    )
    db.session.commit()

    assert WantedRepository().get_series_low_score_counts() == {1: 2}
