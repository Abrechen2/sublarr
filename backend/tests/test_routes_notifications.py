"""Tests for routes/notifications_mgmt.py — template CRUD and Jinja2 validation."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_TEMPLATE = {
    "id": 1,
    "name": "Download Complete",
    "title_template": "Downloaded {{ title }}",
    "body_template": "Subtitle downloaded for {{ title }} ({{ language }})",
    "event_type": "download_complete",
    "service_name": None,
    "enabled": 1,
}

# Patch target: NotificationRepository is imported lazily inside each route function.
# The module under test imports it via `from db.repositories.notifications import ...`
# so we patch the class at its source location.
REPO_PATCH = "db.repositories.notifications.NotificationRepository"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# TestValidateJinja2Syntax — pure function, no HTTP
# ---------------------------------------------------------------------------


class TestValidateJinja2Syntax:
    """Unit tests for the _validate_jinja2_syntax helper."""

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from routes.notifications_mgmt import _validate_jinja2_syntax

        self.validate = _validate_jinja2_syntax

    def test_valid_template_returns_none(self):
        assert self.validate("Hello {{ name }}") is None

    def test_empty_string_returns_none(self):
        assert self.validate("") is None

    def test_none_returns_none(self):
        assert self.validate(None) is None

    def test_invalid_if_block_returns_error_string(self):
        result = self.validate("{% if %}")
        assert result is not None
        assert isinstance(result, str)

    def test_valid_for_loop_returns_none(self):
        assert self.validate("{% for item in items %}{{ item }}{% endfor %}") is None

    def test_unclosed_for_block_returns_error_string(self):
        result = self.validate("{% for item in items %}{{ item }}")
        assert result is not None
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# TestListTemplates — GET /api/v1/notifications/templates
# ---------------------------------------------------------------------------


class TestListTemplates:
    def test_returns_all_templates(self, client):
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = [SAMPLE_TEMPLATE]
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/templates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Download Complete"

    def test_returns_empty_list_when_no_templates(self, client):
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = []
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/templates")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_event_type_filter_forwarded_to_repo(self, client):
        mock_repo = MagicMock()
        mock_repo.get_templates.return_value = []
        with patch(REPO_PATCH, return_value=mock_repo):
            client.get("/api/v1/notifications/templates?event_type=download_complete")
        mock_repo.get_templates.assert_called_once_with(event_type="download_complete")


# ---------------------------------------------------------------------------
# TestCreateTemplate — POST /api/v1/notifications/templates
# ---------------------------------------------------------------------------


class TestCreateTemplate:
    def test_400_when_name_missing(self, client):
        mock_repo = MagicMock()
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/templates",
                json={"title_template": "Hello"},
            )
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_400_when_title_template_invalid_jinja2(self, client):
        mock_repo = MagicMock()
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/templates",
                json={"name": "Bad Title", "title_template": "{% if %}"},
            )
        assert resp.status_code == 400
        assert "title" in resp.get_json()["error"].lower()

    def test_400_when_body_template_invalid_jinja2(self, client):
        mock_repo = MagicMock()
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/templates",
                json={"name": "Bad Body", "body_template": "{% for item %}"},
            )
        assert resp.status_code == 400
        assert "body" in resp.get_json()["error"].lower()

    def test_201_on_success(self, client):
        mock_repo = MagicMock()
        mock_repo.create_template.return_value = SAMPLE_TEMPLATE
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/templates",
                json={
                    "name": "Download Complete",
                    "title_template": "Downloaded {{ title }}",
                    "body_template": "Body {{ language }}",
                    "event_type": "download_complete",
                },
            )
        assert resp.status_code == 201
        assert resp.get_json()["name"] == "Download Complete"

    def test_valid_complex_jinja2_accepted(self, client):
        mock_repo = MagicMock()
        mock_repo.create_template.return_value = SAMPLE_TEMPLATE
        complex_template = (
            "{% if title %}{{ title | upper }}{% else %}Unknown{% endif %} "
            "{% for tag in tags %}[{{ tag }}]{% endfor %}"
        )
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/templates",
                json={"name": "Complex", "body_template": complex_template},
            )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# TestGetTemplate — GET /api/v1/notifications/templates/<id>
# ---------------------------------------------------------------------------


class TestGetTemplate:
    def test_200_with_template_when_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = SAMPLE_TEMPLATE
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/templates/1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1
        assert data["name"] == "Download Complete"

    def test_404_when_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = None
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/templates/999")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestUpdateTemplate — PUT /api/v1/notifications/templates/<id>
# ---------------------------------------------------------------------------


class TestUpdateTemplate:
    def test_404_when_template_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = None
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/templates/999",
                json={"name": "New Name"},
            )
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()

    def test_400_invalid_title_template_syntax(self, client):
        mock_repo = MagicMock()
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/templates/1",
                json={"title_template": "{% if %}"},
            )
        assert resp.status_code == 400
        assert "title" in resp.get_json()["error"].lower()

    def test_400_invalid_body_template_syntax(self, client):
        mock_repo = MagicMock()
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/templates/1",
                json={"body_template": "{% for x %}broken"},
            )
        assert resp.status_code == 400
        assert "body" in resp.get_json()["error"].lower()

    def test_200_on_success_with_updated_data(self, client):
        updated = {**SAMPLE_TEMPLATE, "name": "Updated Name"}
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = updated
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/templates/1",
                json={"name": "Updated Name"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Updated Name"

    def test_unknown_fields_ignored(self, client):
        """Fields not in the allowed set must not be forwarded to the repo."""
        updated = {**SAMPLE_TEMPLATE}
        mock_repo = MagicMock()
        mock_repo.update_template.return_value = updated
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/templates/1",
                json={"name": "Valid", "injected_field": "bad"},
            )
        assert resp.status_code == 200
        # Verify the repo was NOT called with the unknown field
        call_kwargs = mock_repo.update_template.call_args[1]
        assert "injected_field" not in call_kwargs


# ---------------------------------------------------------------------------
# TestDeleteTemplate — DELETE /api/v1/notifications/templates/<id>
# ---------------------------------------------------------------------------


class TestDeleteTemplate:
    def test_200_on_success(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_template.return_value = True
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.delete("/api/v1/notifications/templates/1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_404_when_not_found(self, client):
        """Route returns 404 when repo.delete_template returns falsy."""
        mock_repo = MagicMock()
        mock_repo.delete_template.return_value = False
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.delete("/api/v1/notifications/templates/999")
        assert resp.status_code == 404
        assert "not found" in resp.get_json()["error"].lower()
