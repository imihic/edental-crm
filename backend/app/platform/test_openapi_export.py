import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_openapi_export_is_current(app, tmp_path):
    out = tmp_path / "openapi.json"
    result = app.test_cli_runner().invoke(args=["export-openapi", str(out)])
    assert result.exit_code == 0, result.output
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert exported == app.api_doc
    committed = REPO_ROOT / "openapi.json"
    assert committed.exists(), "run: flask export-openapi ../openapi.json"
    assert json.loads(committed.read_text(encoding="utf-8")) == exported, (
        "openapi.json is stale; run: flask export-openapi ../openapi.json"
    )


def test_auth_endpoints_are_documented(app):
    paths = app.api_doc["paths"]
    for path, method in [
        ("/api/auth/csrf", "get"),
        ("/api/auth/login", "post"),
        ("/api/auth/organizations", "get"),
        ("/api/auth/organization", "post"),
        ("/api/auth/me", "get"),
        ("/api/auth/logout", "post"),
        ("/api/auth/totp", "post"),
        ("/api/auth/totp/enroll", "post"),
        ("/api/auth/totp/confirm", "post"),
    ]:
        assert method in paths.get(path, {}), f"{method.upper()} {path} missing from OpenAPI"
    assert not [p for p in paths if "_test" in p], "test probe must stay out of the OpenAPI export"


def test_validation_error_documented_with_its_real_shape(app):
    for path, item in app.api_doc["paths"].items():
        for method, op in item.items():
            schema = op["responses"]["422"]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ValidationErrorResponse"}, (method, path)
