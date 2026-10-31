"""Routes that take a file path apply the configured path mapping.

Audit #61 A26: the spell check (and, found by the sweep, three video routes)
read ``settings.media_path_mapping`` — a setting that does not exist — so a
path as Sonarr reports it was never mapped and ended in 403/404.
"""

from unittest.mock import patch


def _setup(client, tmp_path):
    local = tmp_path / "tv"
    local.mkdir()
    (local / "Ep.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n", encoding="utf-8")
    response = client.put("/api/v1/config", json={"path_mapping": f"/data/tv={local}"})
    assert response.status_code == 200, response.get_json()
    return local


def test_the_spell_check_maps_a_remote_path(client, tmp_path):
    local = _setup(client, tmp_path)

    with patch("routes.spell.check_subtitle_file", return_value={"errors": []}) as check:
        response = client.post(
            "/api/v1/spell/check", json={"file_path": "/data/tv/Ep.de.srt", "language": "de_DE"}
        )

    assert response.status_code == 200, response.get_json()
    assert check.call_args.args[0] == str(local / "Ep.de.srt")


def test_no_route_reads_the_setting_that_does_not_exist():
    import ast
    import pathlib

    routes = pathlib.Path(__file__).resolve().parents[1] / "routes"
    offenders = []
    for path in routes.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            reads = (isinstance(node, ast.Attribute) and node.attr == "media_path_mapping") or (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", "") in ("getattr", "hasattr")
                and any(getattr(a, "value", None) == "media_path_mapping" for a in node.args)
            )
            if reads:
                offenders.append(f"{path.relative_to(routes)}:{node.lineno}")
    assert offenders == []
