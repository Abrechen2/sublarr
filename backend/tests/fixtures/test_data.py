"""Test data fixtures for Sublarr tests."""

from typing import Any, Dict

# Sample video query data
SAMPLE_VIDEO_QUERY = {
    "series": "Attack on Titan",
    "season": 1,
    "episode": 1,
    "year": 2013,
    "language": "en",
    "imdb_id": "1234567",
    "tmdb_id": 12345,
    "anidb_id": 1234,
    "release_group": "FansubGroup",
    "resolution": "1080p",
    "source": "BluRay",
    "codec": "x264",
}

# Sample series data
SAMPLE_SERIES = {
    "id": 1,
    "title": "Attack on Titan",
    "tvdb_id": 12345,
    "imdb_id": "tt1234567",
    "tmdb_id": 12345,
    "year": 2013,
    "path": "/media/anime/Attack on Titan",
    "monitored": True,
    "season_folder": True,
}

# Sample episode data
SAMPLE_EPISODE = {
    "id": 1,
    "series_id": 1,
    "season_number": 1,
    "episode_number": 1,
    "title": "To You, in 2000 Years",
    "air_date": "2013-04-07",
    "file_path": "/media/anime/Attack on Titan/Season 01/Attack.on.Titan.S01E01.1080p.BluRay.x264.mkv",
    "file_size": 1073741824,  # 1GB
    "quality": "BluRay-1080p",
}

# Sample movie data
SAMPLE_MOVIE = {
    "id": 1,
    "title": "Your Name",
    "year": 2016,
    "imdb_id": "tt5311514",
    "tmdb_id": 372058,
    "path": "/media/movies/Your Name (2016)",
    "monitored": True,
}

# Sample language profile
SAMPLE_LANGUAGE_PROFILE = {
    "id": 1,
    "name": "German (Anime)",
    "languages": ["de"],
    "min_score": 200,
    "prefer_ass": True,
    "hi_removal": True,
}

# Sample glossary entry
SAMPLE_GLOSSARY_ENTRY = {
    "id": 1,
    "series_id": 1,
    "source_term": "Titan",
    "target_term": "Titan",
    "case_sensitive": False,
    "regex": False,
}

# Sample config entry
SAMPLE_CONFIG_ENTRY = {
    "key": "test_config_key",
    "value": "test_config_value",
    "description": "Test configuration entry",
}

# Sample wanted item
SAMPLE_WANTED_ITEM = {
    "id": 1,
    "item_type": "episode",
    "series_id": 1,
    "episode_id": 1,
    "file_path": "/media/anime/Attack on Titan/Season 01/Attack.on.Titan.S01E01.1080p.BluRay.x264.mkv",
    "target_language": "de",
    "status": "wanted",
    "search_count": 0,
}

# Sample subtitle download
SAMPLE_SUBTITLE_DOWNLOAD = {
    "id": 1,
    "file_path": "/media/anime/Attack on Titan/Season 01/Attack.on.Titan.S01E01.1080p.BluRay.x264.de.ass",
    "provider_name": "opensubtitles",
    "subtitle_id": "12345",
    "language": "de",
    "format": "ass",
    "score": 250,
    "downloaded_at": "2024-01-15T10:30:00Z",
}

# Sample webhook payloads
SONARR_WEBHOOK_PAYLOAD = {
    "eventType": "Download",
    "series": SAMPLE_SERIES,
    "episodes": [SAMPLE_EPISODE],
    "episodeFile": {
        "id": 1,
        "path": "/media/anime/Attack on Titan/Season 01/Attack.on.Titan.S01E01.1080p.BluRay.x264.mkv",
        "quality": "BluRay-1080p",
        "size": 1073741824,
    },
}

RADARR_WEBHOOK_PAYLOAD = {
    "eventType": "Download",
    "movie": SAMPLE_MOVIE,
    "movieFile": {
        "id": 1,
        "path": "/media/movies/Your Name (2016)/Your.Name.2016.1080p.BluRay.x264.mkv",
        "quality": "BluRay-1080p",
        "size": 2147483648,  # 2GB
    },
}


# Helper function to create test data
def create_test_video_query(**overrides) -> dict[str, Any]:
    """Create a test video query with optional overrides."""
    query = SAMPLE_VIDEO_QUERY.copy()
    query.update(overrides)
    return query


def create_test_series(**overrides) -> dict[str, Any]:
    """Create a test series with optional overrides."""
    series = SAMPLE_SERIES.copy()
    series.update(overrides)
    return series


def create_test_episode(**overrides) -> dict[str, Any]:
    """Create a test episode with optional overrides."""
    episode = SAMPLE_EPISODE.copy()
    episode.update(overrides)
    return episode
