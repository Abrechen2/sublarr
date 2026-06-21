from unittest.mock import patch

from services.subtitle_health import apply


def test_dispatch_repair_escapes_sidecar(app_ctx):
    finding = {
        "id": 7,
        "target_kind": "sidecar",
        "target_path": "/m/x.de.srt",
        "stream_index": None,
        "lang": "de",
    }
    with (
        patch("services.subtitle_health.apply.store.get_finding", return_value=finding),
        patch(
            "services.subtitle_health.fixers.repair_escapes.apply_to_sidecar",
            return_value={"changed": True, "fix_id": 1},
        ) as fx,
    ):
        res = apply.apply_fix(finding_id=7, action="repair_escapes")
    assert res["changed"] is True
    assert fx.called


def test_unknown_action_rejected(app_ctx):
    with patch(
        "services.subtitle_health.apply.store.get_finding",
        return_value={"id": 1, "target_kind": "sidecar", "target_path": "/m/x", "lang": "de"},
    ):
        res = apply.apply_fix(finding_id=1, action="nope")
    assert res["changed"] is False
    assert "unknown" in res["reason"].lower()
