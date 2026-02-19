"""Search repository -- FTS5 trigram full-text search across all entities."""

import logging
from sqlalchemy import text
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# FTS5 virtual table schema -- created once at app startup
_SEARCH_SCHEMA = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_series
       USING fts5(id UNINDEXED, title, tokenize="trigram")""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_episodes
       USING fts5(id UNINDEXED, series_id UNINDEXED, title, season_episode, tokenize="trigram")""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_subtitles
       USING fts5(id UNINDEXED, file_path, provider_name, language, tokenize="trigram")""",
]


class SearchRepository(BaseRepository):
    """Full-text search across series, episodes, and subtitles using FTS5."""

    def init_search_tables(self) -> None:
        """Create FTS5 virtual tables. Call from app.py after db.create_all()."""
        with self.session.bind.connect() as conn:
            for stmt in _SEARCH_SCHEMA:
                conn.execute(text(stmt))
            conn.commit()

    def rebuild_index(self) -> None:
        """Rebuild FTS5 tables from subtitle_downloads. Call after library sync."""
        with self.session.bind.connect() as conn:
            # subtitle_downloads is the primary DB-backed entity for search
            conn.execute(text("DELETE FROM search_subtitles"))
            conn.execute(text("""
                INSERT INTO search_subtitles(id, file_path, provider_name, language)
                SELECT id, file_path, provider_name, language
                FROM subtitle_downloads
            """))
            # wanted_items title search (series/episode titles come from here)
            conn.execute(text("DELETE FROM search_episodes"))
            conn.execute(text("""
                INSERT INTO search_episodes(id, series_id, title, season_episode)
                SELECT id, COALESCE(sonarr_series_id, radarr_movie_id, 0),
                       title, season_episode
                FROM wanted_items
                WHERE title IS NOT NULL AND title != ''
            """))
            # series search: deduplicated series titles from wanted_items
            conn.execute(text("DELETE FROM search_series"))
            conn.execute(text("""
                INSERT INTO search_series(id, title)
                SELECT sonarr_series_id, title
                FROM wanted_items
                WHERE sonarr_series_id IS NOT NULL AND title IS NOT NULL
                GROUP BY sonarr_series_id
            """))
            conn.commit()

    def search_all(self, query: str, limit: int = 20) -> dict:
        """FTS5 trigram search across series, episodes, and subtitles.

        Returns grouped results: {"series": [...], "episodes": [...], "subtitles": [...]}.
        Minimum query length is 2 characters (trigram requires 3-char tokens for MATCH;
        LIKE '%q%' works for 2+ chars and uses the trigram index).
        """
        if not query or len(query.strip()) < 2:
            return {"series": [], "episodes": [], "subtitles": []}

        like_term = f"%{query.strip()}%"
        with self.session.bind.connect() as conn:
            series = conn.execute(
                text("SELECT id, title FROM search_series WHERE title LIKE :q LIMIT :lim"),
                {"q": like_term, "lim": limit}
            ).mappings().all()

            episodes = conn.execute(
                text("""SELECT id, series_id, title, season_episode
                        FROM search_episodes
                        WHERE title LIKE :q OR season_episode LIKE :q LIMIT :lim"""),
                {"q": like_term, "lim": limit}
            ).mappings().all()

            subtitles = conn.execute(
                text("""SELECT id, file_path, provider_name, language
                        FROM search_subtitles
                        WHERE file_path LIKE :q OR provider_name LIKE :q LIMIT :lim"""),
                {"q": like_term, "lim": limit}
            ).mappings().all()

        return {
            "series": [dict(r) for r in series],
            "episodes": [dict(r) for r in episodes],
            "subtitles": [dict(r) for r in subtitles],
        }
