"""Opt-in anonymous usage-statistics consent API.

GET  /api/v1/usage-stats/consent  -> {"consent": "unset|granted|denied"}
POST /api/v1/usage-stats/consent  {"consent": "granted|denied"} -> {"consent": ...}
"""

from flask import jsonify, request

from routes.system import bp
from services.background_tasks import submit_background
from services.usage_stats import get_consent, set_consent, usage_stats_tick


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
        # without waiting up to 24h for the scheduled tick.
        submit_background(usage_stats_tick)
    return jsonify({"consent": value})
