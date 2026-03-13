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


class TestFansubPrefsRoutes:
    def test_get_unknown_series_returns_defaults(self, client):
        r = client.get("/api/v1/series/999/fansub-prefs")
        assert r.status_code == 200
        data = r.get_json()
        assert data["series_id"] == 999
        assert data["preferred_groups"] == []
        assert data["excluded_groups"] == []
        assert data["bonus"] == 20

    def test_put_sets_prefs(self, client):
        r = client.put(
            "/api/v1/series/42/fansub-prefs",
            json={"preferred_groups": ["SubsPlease"], "excluded_groups": [], "bonus": 25},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["preferred_groups"] == ["SubsPlease"]
        assert data["bonus"] == 25

    def test_get_after_put_returns_saved_prefs(self, client):
        client.put(
            "/api/v1/series/43/fansub-prefs",
            json={
                "preferred_groups": ["Erai-raws"],
                "excluded_groups": ["HorribleSubs"],
                "bonus": 15,
            },
        )
        r = client.get("/api/v1/series/43/fansub-prefs")
        assert r.status_code == 200
        data = r.get_json()
        assert data["preferred_groups"] == ["Erai-raws"]
        assert data["excluded_groups"] == ["HorribleSubs"]

    def test_put_invalid_bonus_rejected(self, client):
        r = client.put(
            "/api/v1/series/44/fansub-prefs",
            json={"preferred_groups": [], "excluded_groups": [], "bonus": "bad"},
        )
        assert r.status_code == 400

    def test_put_groups_must_be_lists(self, client):
        r = client.put(
            "/api/v1/series/45/fansub-prefs",
            json={"preferred_groups": "SubsPlease", "excluded_groups": [], "bonus": 10},
        )
        assert r.status_code == 400

    def test_delete_clears_prefs(self, client):
        client.put(
            "/api/v1/series/46/fansub-prefs",
            json={"preferred_groups": ["X"], "excluded_groups": [], "bonus": 5},
        )
        r = client.delete("/api/v1/series/46/fansub-prefs")
        assert r.status_code == 200
        r2 = client.get("/api/v1/series/46/fansub-prefs")
        assert r2.get_json()["preferred_groups"] == []
