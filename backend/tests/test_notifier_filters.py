"""Tests for notifier dispatcher filter enforcement (F1 — wiring fix).

The Filters UI persists `notification_filter_include_events` and
`notification_filter_exclude_events` config_entries. Before this fix
the dispatcher never read them, so saved filters were purely cosmetic.
These tests pin the new behaviour: include/exclude lists must short-
circuit `send_notification` BEFORE Apprise dispatch.
"""

from unittest.mock import MagicMock, patch


def _make_settings(**overrides):
    """Build a settings-stub with all event toggles ON by default."""
    s = MagicMock()
    s.notify_on_download = True
    s.notify_on_upgrade = True
    s.notify_on_batch_complete = True
    s.notify_on_error = True
    s.notify_manual_actions = True
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _stub_repo_no_quiet_no_template():
    """Stub NotificationRepository: no quiet hours, no template."""
    repo = MagicMock()
    repo.is_quiet_hours.return_value = False
    repo.find_template_for_event.return_value = None
    repo.log_notification.return_value = {}
    return repo


def _stub_config_repo(include=None, exclude=None):
    """Stub ConfigRepository.get_config_entry to return given filter lists.

    Pass None to omit a key entirely (simulates "user never saved that
    filter"); pass an empty list to simulate "user cleared the filter".
    """
    import json as _json

    cfg_repo = MagicMock()

    def _get(key):
        if key == "notification_filter_include_events":
            return _json.dumps(include) if include is not None else None
        if key == "notification_filter_exclude_events":
            return _json.dumps(exclude) if exclude is not None else None
        return None

    cfg_repo.get_config_entry.side_effect = _get
    return cfg_repo


# ─── Direct unit tests for _is_event_filtered ─────────────────────────────────


def test_is_event_filtered_returns_false_when_no_filters_saved():
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(include=None, exclude=None)
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("download") is False


def test_is_event_filtered_returns_true_when_event_in_exclude_list():
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(exclude=["error"])
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("error") is True


def test_is_event_filtered_returns_false_when_event_not_in_exclude_list():
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(exclude=["upgrade"])
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("download") is False


def test_is_event_filtered_returns_true_when_include_set_and_event_missing():
    """Non-empty include list = whitelist. Events outside it must be filtered."""
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(include=["download"])
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("error") is True


def test_is_event_filtered_returns_false_when_include_set_and_event_present():
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(include=["download", "upgrade"])
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("download") is False


def test_is_event_filtered_treats_empty_include_list_as_no_whitelist():
    """An empty include list must NOT block events (means: nothing whitelisted = pass-through)."""
    from notifier import _is_event_filtered

    cfg_repo = _stub_config_repo(include=[])
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        assert _is_event_filtered("download") is False


def test_is_event_filtered_swallows_repo_errors():
    """Filter check failure must not block notification delivery."""
    from notifier import _is_event_filtered

    cfg_repo = MagicMock()
    cfg_repo.get_config_entry.side_effect = RuntimeError("DB outage")
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        # Hard exception inside _is_event_filtered must result in False
        # (i.e. don't filter — fail open so the user still gets notified).
        assert _is_event_filtered("download") is False


def test_is_event_filtered_swallows_invalid_json():
    """Garbage JSON in config must be treated as 'no filter set'."""
    from notifier import _is_event_filtered

    cfg_repo = MagicMock()
    cfg_repo.get_config_entry.return_value = "not-json"
    with patch("db.repositories.config.ConfigRepository", return_value=cfg_repo):
        # Bad data → empty list → no filter applied
        assert _is_event_filtered("download") is False


# ─── Integration with send_notification ───────────────────────────────────────


def test_send_notification_short_circuits_before_apprise_when_excluded():
    """Excluded events must not reach Apprise."""
    from notifier import send_notification

    apprise_mock = MagicMock()
    cfg_repo = _stub_config_repo(exclude=["error"])

    with (
        patch("config.get_settings", return_value=_make_settings()),
        patch("db.repositories.config.ConfigRepository", return_value=cfg_repo),
        patch(
            "db.repositories.notifications.NotificationRepository",
            return_value=_stub_repo_no_quiet_no_template(),
        ),
        patch("notifier._get_apprise", return_value=apprise_mock),
    ):
        send_notification(title="t", body="b", event_type="error")

    # Apprise must NOT have been called — the filter cut the dispatch.
    apprise_mock.notify.assert_not_called()


def test_send_notification_proceeds_when_event_passes_filters():
    """Events that pass include + exclude lists reach Apprise as before."""
    from notifier import send_notification

    apprise_mock = MagicMock()
    cfg_repo = _stub_config_repo(include=["download"], exclude=[])

    with (
        patch("config.get_settings", return_value=_make_settings()),
        patch("db.repositories.config.ConfigRepository", return_value=cfg_repo),
        patch(
            "db.repositories.notifications.NotificationRepository",
            return_value=_stub_repo_no_quiet_no_template(),
        ),
        patch("notifier._get_apprise", return_value=apprise_mock),
    ):
        send_notification(title="t", body="b", event_type="download")

    apprise_mock.notify.assert_called_once()


def test_send_notification_blocks_event_outside_include_list():
    """Whitelist gate: event not in include_events is dropped."""
    from notifier import send_notification

    apprise_mock = MagicMock()
    cfg_repo = _stub_config_repo(include=["download"])

    with (
        patch("config.get_settings", return_value=_make_settings()),
        patch("db.repositories.config.ConfigRepository", return_value=cfg_repo),
        patch(
            "db.repositories.notifications.NotificationRepository",
            return_value=_stub_repo_no_quiet_no_template(),
        ),
        patch("notifier._get_apprise", return_value=apprise_mock),
    ):
        send_notification(title="t", body="b", event_type="error")

    apprise_mock.notify.assert_not_called()
