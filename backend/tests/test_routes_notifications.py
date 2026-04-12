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


# ---------------------------------------------------------------------------
# TestPreviewTemplate — POST /api/v1/notifications/templates/<id>/preview
# ---------------------------------------------------------------------------


class TestPreviewTemplate:
    def test_404_when_template_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = None
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post("/api/v1/notifications/templates/999/preview", json={})
        assert resp.status_code == 404

    def test_200_with_rendered_output(self, client):
        template = {
            **SAMPLE_TEMPLATE,
            "title_template": "Downloaded {{ title }}",
            "body_template": "Language: {{ language }}",
        }
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = template

        with (
            patch(REPO_PATCH, return_value=mock_repo),
            patch("notifier.get_sample_payload", return_value={"title": "Naruto", "language": "de"}),
            patch("notifier.render_template", side_effect=lambda tpl, vars: tpl),
        ):
            resp = client.post("/api/v1/notifications/templates/1/preview", json={})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "title" in data
        assert "body" in data
        assert "variables_used" in data

    def test_custom_variables_override_sample(self, client):
        template = {**SAMPLE_TEMPLATE, "event_type": "download_complete"}
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = template

        captured_vars = {}

        def fake_render(tpl, variables):
            captured_vars.update(variables)
            return "rendered"

        with (
            patch(REPO_PATCH, return_value=mock_repo),
            patch(
                "notifier.get_sample_payload",
                return_value={"title": "Sample Title", "language": "en"},
            ),
            patch("notifier.render_template", side_effect=fake_render),
        ):
            resp = client.post(
                "/api/v1/notifications/templates/1/preview",
                json={"variables": {"title": "Custom Title"}},
            )
        assert resp.status_code == 200
        assert captured_vars["title"] == "Custom Title"

    def test_400_on_render_error(self, client):
        template = {**SAMPLE_TEMPLATE, "event_type": ""}
        mock_repo = MagicMock()
        mock_repo.get_template.return_value = template

        with (
            patch(REPO_PATCH, return_value=mock_repo),
            patch("notifier.render_template", side_effect=Exception("render failed")),
        ):
            resp = client.post("/api/v1/notifications/templates/1/preview", json={})
        assert resp.status_code == 400
        assert "render" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestListVariables — GET /api/v1/notifications/variables
# ---------------------------------------------------------------------------


class TestListVariables:
    def test_returns_variables_grouped_by_event(self, client):
        catalog = {
            "download_complete": {
                "label": "Download Complete",
                "description": "Fired after download",
                "payload_keys": ["title", "language", "provider"],
            }
        }
        with patch("events.catalog.EVENT_CATALOG", catalog):
            resp = client.get("/api/v1/notifications/variables")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "download_complete" in data
        assert data["download_complete"]["variables"] == ["title", "language", "provider"]

    def test_empty_catalog(self, client):
        with patch("events.catalog.EVENT_CATALOG", {}):
            resp = client.get("/api/v1/notifications/variables")
        assert resp.status_code == 200
        assert resp.get_json() == {}


# ---------------------------------------------------------------------------
# TestGetVariables — GET /api/v1/notifications/variables/<event_type>
# ---------------------------------------------------------------------------


class TestGetVariables:
    def test_200_for_known_event(self, client):
        catalog = {
            "download_complete": {
                "label": "Download Complete",
                "description": "Desc",
                "payload_keys": ["title"],
            }
        }
        with patch("events.catalog.EVENT_CATALOG", catalog):
            resp = client.get("/api/v1/notifications/variables/download_complete")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["event_type"] == "download_complete"
        assert "title" in data["variables"]

    def test_404_for_unknown_event(self, client):
        with patch("events.catalog.EVENT_CATALOG", {}):
            resp = client.get("/api/v1/notifications/variables/nonexistent")
        assert resp.status_code == 404
        assert "unknown" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestQuietHours — CRUD /api/v1/notifications/quiet-hours
# ---------------------------------------------------------------------------

QUIET_HOURS_SAMPLE = {
    "id": 1,
    "name": "Night",
    "start_time": "22:00",
    "end_time": "07:00",
    "days_of_week": "[0,1,2,3,4,5,6]",
    "exception_events": '["error"]',
    "enabled": 1,
}


class TestQuietHoursList:
    def test_returns_all_configs(self, client):
        mock_repo = MagicMock()
        mock_repo.get_quiet_hours_configs.return_value = [QUIET_HOURS_SAMPLE]
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/quiet-hours")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 1


class TestQuietHoursCreate:
    def test_400_when_name_missing(self, client):
        resp = client.post(
            "/api/v1/notifications/quiet-hours",
            json={"start_time": "22:00", "end_time": "07:00"},
        )
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"]

    def test_400_when_times_missing(self, client):
        resp = client.post(
            "/api/v1/notifications/quiet-hours",
            json={"name": "Night"},
        )
        assert resp.status_code == 400
        assert "time" in resp.get_json()["error"].lower()

    def test_400_invalid_start_time_format(self, client):
        resp = client.post(
            "/api/v1/notifications/quiet-hours",
            json={"name": "Night", "start_time": "10pm", "end_time": "07:00"},
        )
        assert resp.status_code == 400
        assert "HH:MM" in resp.get_json()["error"]

    def test_400_invalid_end_time_format(self, client):
        resp = client.post(
            "/api/v1/notifications/quiet-hours",
            json={"name": "Night", "start_time": "22:00", "end_time": "7"},
        )
        assert resp.status_code == 400
        assert "HH:MM" in resp.get_json()["error"]

    def test_201_on_success(self, client):
        mock_repo = MagicMock()
        mock_repo.create_quiet_hours.return_value = QUIET_HOURS_SAMPLE
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post(
                "/api/v1/notifications/quiet-hours",
                json={"name": "Night", "start_time": "22:00", "end_time": "07:00"},
            )
        assert resp.status_code == 201
        assert resp.get_json()["name"] == "Night"


class TestQuietHoursUpdate:
    def test_404_when_config_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.update_quiet_hours.return_value = None
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/quiet-hours/999",
                json={"name": "Updated"},
            )
        assert resp.status_code == 404

    def test_400_invalid_time_in_update(self, client):
        resp = client.put(
            "/api/v1/notifications/quiet-hours/1",
            json={"start_time": "bad"},
        )
        assert resp.status_code == 400

    def test_200_on_success(self, client):
        updated = {**QUIET_HOURS_SAMPLE, "name": "Updated Night"}
        mock_repo = MagicMock()
        mock_repo.update_quiet_hours.return_value = updated
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/quiet-hours/1",
                json={"name": "Updated Night"},
            )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "Updated Night"


class TestQuietHoursDelete:
    def test_200_on_success(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_quiet_hours.return_value = True
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.delete("/api/v1/notifications/quiet-hours/1")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_404_when_config_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_quiet_hours.return_value = False
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.delete("/api/v1/notifications/quiet-hours/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TestHistory — GET/DELETE /api/v1/notifications/history
# ---------------------------------------------------------------------------


class TestNotificationHistory:
    def test_list_returns_paginated_result(self, client):
        mock_result = {"items": [], "total": 0, "page": 1, "per_page": 50}
        mock_repo = MagicMock()
        mock_repo.get_history.return_value = mock_result
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/history")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 0

    def test_list_forwards_pagination_params(self, client):
        mock_repo = MagicMock()
        mock_repo.get_history.return_value = {"items": [], "total": 0, "page": 2, "per_page": 10}
        with patch(REPO_PATCH, return_value=mock_repo):
            client.get("/api/v1/notifications/history?page=2&per_page=10")
        mock_repo.get_history.assert_called_once_with(page=2, per_page=10, event_type=None)

    def test_clear_history_returns_deleted_count(self, client):
        mock_repo = MagicMock()
        mock_repo.clear_history.return_value = 42
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.delete("/api/v1/notifications/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["deleted"] == 42


# ---------------------------------------------------------------------------
# TestResendNotification — POST /api/v1/notifications/history/<id>/resend
# ---------------------------------------------------------------------------


class TestResendNotification:
    def test_404_when_notification_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_notification.return_value = None
        with patch(REPO_PATCH, return_value=mock_repo):
            resp = client.post("/api/v1/notifications/history/999/resend")
        assert resp.status_code == 404

    def test_200_on_resend(self, client):
        notification = {
            "id": 1,
            "title": "Test Title",
            "body": "Test Body",
            "event_type": "download_complete",
        }
        mock_repo = MagicMock()
        mock_repo.get_notification.return_value = notification
        with (
            patch(REPO_PATCH, return_value=mock_repo),
            patch("notifier.send_notification") as mock_send,
        ):
            resp = client.post("/api/v1/notifications/history/1/resend")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        mock_send.assert_called_once_with(
            title="Test Title",
            body="Test Body",
            event_type="download_complete",
            is_manual=True,
        )


# ---------------------------------------------------------------------------
# TestEventFilters — GET/PUT /api/v1/notifications/filters
# ---------------------------------------------------------------------------

CONFIG_REPO_PATCH = "db.repositories.config.ConfigRepository"


class TestEventFilters:
    def test_get_filters_returns_defaults_when_empty(self, client):
        mock_repo = MagicMock()
        mock_repo.get_config_entry.return_value = None
        with patch(CONFIG_REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/filters")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["include_events"] == []
        assert data["exclude_events"] == []
        assert data["content_filters"] == []

    def test_get_filters_parses_stored_json(self, client):
        mock_repo = MagicMock()

        def side_effect(key):
            mapping = {
                "notification_filter_include_events": '["download_complete"]',
                "notification_filter_exclude_events": '["error"]',
                "notification_filter_content_filters": "[]",
            }
            return mapping.get(key)

        mock_repo.get_config_entry.side_effect = side_effect
        with patch(CONFIG_REPO_PATCH, return_value=mock_repo):
            resp = client.get("/api/v1/notifications/filters")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["include_events"] == ["download_complete"]
        assert data["exclude_events"] == ["error"]

    def test_update_filters_saves_to_config(self, client):
        mock_repo = MagicMock()
        with patch(CONFIG_REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/filters",
                json={
                    "include_events": ["download_complete"],
                    "exclude_events": ["error"],
                },
            )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert mock_repo.save_config_entry.call_count == 2

    def test_update_filters_partial_update(self, client):
        """Only provided keys are saved -- missing keys are not touched."""
        mock_repo = MagicMock()
        with patch(CONFIG_REPO_PATCH, return_value=mock_repo):
            resp = client.put(
                "/api/v1/notifications/filters",
                json={"include_events": ["test"]},
            )
        assert resp.status_code == 200
        # Only one save call, not three
        assert mock_repo.save_config_entry.call_count == 1
