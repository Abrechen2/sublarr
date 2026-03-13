from db.models.core import ChapterCache


class TestChapterCacheModel:
    def test_tablename(self):
        assert ChapterCache.__tablename__ == "chapter_cache"

    def test_has_required_columns(self):
        cols = {c.key for c in ChapterCache.__table__.columns}
        assert "file_path" in cols
        assert "mtime" in cols
        assert "chapters_json" in cols
        assert "cached_at" in cols
