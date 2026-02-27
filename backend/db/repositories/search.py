"""Search repository -- full-text search across all entities.

SQLite backend:  FTS5 virtual tables with trigram tokenizer.
PostgreSQL backend: regular tables with pg_trgm GIN indexes.
The LIKE-based search_all() queries are compatible with both.
"""

import logging

from sqlalchemy import text

from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# SQLite FTS5 virtual table schema
_SQLITE_SEARCH_SCHEMA = [
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_series
       USING fts5(id UNINDEXED, title, tokenize="trigram")""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_episodes
       USING fts5(id UNINDEXED, series_id UNINDEXED, title, season_episode, tokenize="trigram")""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS search_subtitles
       USING fts5(id UNINDEXED, file_path, provider_name, language, tokenize="trigram")""",
]

# PostgreSQL schema: regular tables + pg_trgm GIN indexes for LIKE performance
_POSTGRESQL_SEARCH_SCHEMA = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    """CREATE TABLE IF NOT EXISTS search_series (
       id INTEGER NOT NULL, title TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_ss_title ON search_series USING gin(title gin_trgm_ops)",
    """CREATE TABLE IF NOT EXISTS search_episodes (
       id INTEGER NOT NULL, series_id INTEGER, title TEXT, season_episode TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_se_title ON search_episodes USING gin(title gin_trgm_ops)",
    """CREATE TABLE IF NOT EXISTS search_subtitles (
       id INTEGER NOT NULL, file_path TEXT, provider_name TEXT, language TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_st_path ON search_subtitles USING gin(file_path gin_trgm_ops)",
]


def _get_engine():
    """Get the SQLAlchemy engine from Flask-SQLAlchemy extension."""
    from extensions import db as sa_db
    return sa_db.engine


def _is_postgresql(engine) -> bool:
    return engine.dialect.name == "postgresql"


class SearchRepository(BaseRepository):
    """Full-text search across series, episodes, and subtitles."""

    def init_search_tables(self) -> None:
        """Create search tables. Call from app.py after db.create_all()."""
        engine = _get_engine()
        stmts = _POSTGRESQL_SEARCH_SCHEMA if _is_postgresql(engine) else _SQLITE_SEARCH_SCHEMA
        with engine.connect() as conn:
            for stmt in stmts:
                conn.execute(text(stmt))
            conn.commit()

    def rebuild_index(self) -> None:
        """Rebuild search tables from subtitle_downloads. Call after library sync."""
        with _get_engine().connect() as conn:
            conn.execute(text("DELETE FROM search_subtitles"))
            conn.execute(text("""
                INSERT INTO search_subtitles(id, file_path, provider_name, language)
                SELECT id, file_path, provider_name, language
                FROM subtitle_downloads
            """))
            conn.execute(text("DELETE FROM search_episodes"))
            conn.execute(text("""
                INSERT INTO search_episodes(id, series_id, title, season_episode)
                SELECT id, COALESCE(sonarr_series_id, radarr_movie_id, 0),
                       title, season_episode
                FROM wanted_items
                WHERE title IS NOT NULL AND title != ''
            """))
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
        """Trigram search across series, episodes, and subtitles.

        Returns grouped results: {"series": [...], "episodes": [...], "subtitles": [...]}.
        Minimum query length is 2 characters.
        """
        if not query or len(query.strip()) < 2:
            return {"series": [], "episodes": [], "subtitles": []}

        like_term = f"%{query.strip()}%"
        with _get_engine().connect() as conn:
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
