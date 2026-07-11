"""Regression tests for hook/webhook event dispatcher lifecycle."""

from app import create_app


def test_event_dispatchers_disconnect_subscribers_on_shutdown():
    from events.hooks import HookEngine, init_hook_subscribers
    from events.webhooks import WebhookDispatcher, init_webhook_subscribers

    hook_engine = HookEngine(max_workers=1)
    webhook_dispatcher = WebhookDispatcher(max_workers=1)

    init_hook_subscribers(hook_engine)
    init_webhook_subscribers(webhook_dispatcher)

    assert hook_engine._subscriptions
    assert webhook_dispatcher._subscriptions

    hook_engine.shutdown()
    webhook_dispatcher.shutdown()

    assert hook_engine._subscriptions == []
    assert webhook_dispatcher._subscriptions == []

    hook_engine.shutdown()
    webhook_dispatcher.shutdown()


def test_webhook_dispatcher_logs_without_active_app_context(temp_db, monkeypatch):
    from app_shutdown import shutdown_event_dispatchers
    from db.hooks import create_webhook_config, get_hook_logs, get_webhook_config
    from events.webhooks import WebhookDispatcher

    app = create_app(testing=True)
    with app.app_context():
        webhook = create_webhook_config(
            name="test webhook",
            event_name="subtitle_downloaded",
            url="http://example.invalid/webhook",
            retry_count=0,
            timeout_seconds=1,
        )

    dispatcher = WebhookDispatcher(max_workers=1, app=app)
    monkeypatch.setattr(
        dispatcher,
        "send_webhook",
        lambda config, event_name, event_data: {
            "success": True,
            "status_code": 204,
            "error": "",
            "duration_ms": 1,
        },
    )

    try:
        dispatcher._send_and_log(webhook, "subtitle_downloaded", {"provider_name": "test"})

        with app.app_context():
            updated = get_webhook_config(webhook["id"])
            logs = get_hook_logs(webhook_id=webhook["id"])
    finally:
        dispatcher.shutdown()
        shutdown_event_dispatchers(app)

    assert updated["trigger_count"] == 1
    assert updated["last_status_code"] == 204
    assert updated["consecutive_failures"] == 0
    assert logs[0]["hook_type"] == "webhook"
    assert logs[0]["success"] is True
    assert logs[0]["status_code"] == 204
