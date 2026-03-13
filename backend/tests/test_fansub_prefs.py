import pytest

from db.models.core import FansubPreference
from db.repositories.fansub_prefs import FansubPreferenceRepository


class TestFansubPreferenceModel:
    def test_model_has_required_columns(self):
        cols = {c.key for c in FansubPreference.__table__.columns}
        assert "sonarr_series_id" in cols
        assert "preferred_groups_json" in cols
        assert "excluded_groups_json" in cols
        assert "bonus" in cols
        assert "updated_at" in cols

    def test_tablename(self):
        assert FansubPreference.__tablename__ == "fansub_preferences"


class TestFansubPreferenceRepository:
    def test_get_returns_none_for_unknown_series(self, app_ctx):
        repo = FansubPreferenceRepository()
        assert repo.get_fansub_prefs(series_id=9001) is None

    def test_set_and_get_roundtrip(self, app_ctx):
        repo = FansubPreferenceRepository()
        repo.set_fansub_prefs(
            series_id=100,
            preferred=["SubsPlease", "Erai-raws"],
            excluded=["HorribleSubs"],
            bonus=30,
        )
        result = repo.get_fansub_prefs(series_id=100)
        assert result["preferred_groups"] == ["SubsPlease", "Erai-raws"]
        assert result["excluded_groups"] == ["HorribleSubs"]
        assert result["bonus"] == 30

    def test_update_replaces_existing(self, app_ctx):
        repo = FansubPreferenceRepository()
        repo.set_fansub_prefs(series_id=101, preferred=["GroupA"], excluded=[], bonus=20)
        repo.set_fansub_prefs(series_id=101, preferred=["GroupB"], excluded=[], bonus=10)
        result = repo.get_fansub_prefs(series_id=101)
        assert result["preferred_groups"] == ["GroupB"]
        assert result["bonus"] == 10

    def test_set_with_empty_lists(self, app_ctx):
        repo = FansubPreferenceRepository()
        repo.set_fansub_prefs(series_id=102, preferred=[], excluded=[], bonus=0)
        result = repo.get_fansub_prefs(series_id=102)
        assert result["preferred_groups"] == []
        assert result["excluded_groups"] == []

    def test_delete_removes_row(self, app_ctx):
        repo = FansubPreferenceRepository()
        repo.set_fansub_prefs(series_id=103, preferred=["X"], excluded=[], bonus=5)
        repo.delete_fansub_prefs(series_id=103)
        assert repo.get_fansub_prefs(series_id=103) is None
