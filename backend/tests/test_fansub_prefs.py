from db.models.core import FansubPreference


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
