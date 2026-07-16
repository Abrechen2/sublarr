"""Opt-in anonymous usage-statistics consent API.

GET  /api/v1/usage-stats/consent  -> {"consent": "unset|granted|denied"}
POST /api/v1/usage-stats/consent  {"consent": "granted|denied"} -> {"consent": ...}
"""

from flask import current_app, jsonify, request

from routes.system import bp
from services.background_tasks import submit_background
from services.usage_stats import (
    forget_install,
    get_consent,
    get_stats_endpoint,
    set_consent,
    usage_stats_tick,
)


@bp.route("/usage-stats/consent", methods=["GET"])
def usage_stats_consent_get():
    return jsonify({"consent": get_consent()})


@bp.route("/usage-stats/consent", methods=["POST"])
def usage_stats_consent_set():
    data = request.get_json(silent=True) or {}
    value = data.get("consent")
    if value not in ("granted", "denied"):
        return jsonify({"error": "consent must be 'granted' or 'denied'"}), 400
    set_consent(value)
    if value == "granted":
        # Fire one immediate ping so the dashboard reflects the new opt-in
        # without waiting up to 24h for the scheduled tick. submit_background's
        # contract is that the submitted callable pushes its own Flask app
        # context (the pool worker has none); usage_stats_tick touches the DB
        # via build_usage_payload, so wrap it — passing the bare tick silently
        # failed with "working outside of application context".
        _app = current_app._get_current_object()

        def _immediate_ping() -> None:
            with _app.app_context():
                usage_stats_tick()

        submit_background(_immediate_ping)
    elif value == "denied":
        # Right-to-erasure (GDPR Art. 17): withdrawing consent fires one
        # best-effort forget so the stats service drops this install's row.
        # No-op if no endpoint is configured (self-hoster kill-switch). Runs in
        # the background pool, so it needs its own app context (get_or_create_
        # install_id reads config_entries) — same contract as the ping above.
        _app = current_app._get_current_object()

        def _forget() -> None:
            with _app.app_context():
                forget_install(get_stats_endpoint())

        submit_background(_forget)
    return jsonify({"consent": value})
