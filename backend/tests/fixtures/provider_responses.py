"""Mock provider API responses for testing."""

# OpenSubtitles API v2 mock responses
OPENSEARCH_RESPONSE = {
    "data": [
        {
            "id": "12345",
            "type": "subtitle",
            "attributes": {
                "subtitle_id": "12345",
                "language": "en",
                "download_count": 1000,
                "new_download_count": 500,
                "hearing_impaired": False,
                "hd": True,
                "fps": 23.976,
                "votes": 10,
                "rating": 8.5,
                "from_trusted": True,
                "foreign_parts_only": False,
                "upload_date": "2024-01-15T10:30:00Z",
                "ai_translated": False,
                "machine_translated": False,
                "release": "Attack.on.Titan.S01E01.1080p.BluRay.x264",
                "comments": "",
                "legacy_subtitle_id": 12345,
                "uploader": {"uploader_id": 1, "name": "test_uploader", "rank": "trusted"},
                "feature_details": {
                    "feature_id": 123,
                    "feature_type": "episode",
                    "year": 2013,
                    "title": "Attack on Titan",
                    "movie_name": "Attack on Titan - S01E01",
                    "imdb_id": 1234567,
                    "tmdb_id": 12345,
                    "season_number": 1,
                    "episode_number": 1,
                },
                "url": "https://api.opensubtitles.com/api/v1/subtitles/12345",
                "related_links": {
                    "label": "Download",
                    "url": "https://api.opensubtitles.com/api/v1/subtitles/12345/download",
                    "img_url": "",
                },
                "files": [
                    {
                        "file_id": 67890,
                        "cd_number": 1,
                        "file_name": "Attack.on.Titan.S01E01.1080p.BluRay.x264.ass",
                    }
                ],
            },
        }
    ],
    "meta": {"page": 1, "per_page": 1, "total_count": 1, "total_pages": 1},
}

OPENSEARCH_EMPTY_RESPONSE = {
    "data": [],
    "meta": {"page": 1, "per_page": 1, "total_count": 0, "total_pages": 0},
}

# Jimaku mock responses
JIMAKU_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "jimaku-123",
            "anime_id": 12345,
            "episode": 1,
            "language": "en",
            "format": "ass",
            "download_url": "https://jimaku.example.com/download/123",
            "file_name": "Attack.on.Titan.S01E01.ass",
            "release_group": "FansubGroup",
            "score": 180,
        }
    ],
    "total": 1,
}

# AnimeTosho mock responses
ANIMETOSHO_FEED_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <item>
            <title>Attack on Titan S01E01 [FansubGroup]</title>
            <link>https://animetosho.org/view/12345</link>
            <guid>animetosho-12345</guid>
            <description>Subtitle file for Attack on Titan Episode 1</description>
            <pubDate>Mon, 15 Jan 2024 10:30:00 +0000</pubDate>
            <enclosure url="https://animetosho.org/storage/12345.ass" type="application/x-ass"/>
        </item>
    </channel>
</rss>"""

# SubDL mock responses
SUBDL_SEARCH_RESPONSE = {
    "results": [
        {
            "id": "subdl-123",
            "title": "Attack on Titan S01E01",
            "language": "en",
            "format": "ass",
            "download_url": "https://subdl.example.com/download/123",
            "file_name": "Attack.on.Titan.S01E01.ass",
            "score": 150,
        }
    ],
    "total": 1,
}

# Error responses
PROVIDER_ERROR_RESPONSE = {"error": {"code": 500, "message": "Internal server error"}}

PROVIDER_TIMEOUT_RESPONSE = None  # Simulates timeout

PROVIDER_RATE_LIMIT_RESPONSE = {"error": {"code": 429, "message": "Rate limit exceeded"}}
