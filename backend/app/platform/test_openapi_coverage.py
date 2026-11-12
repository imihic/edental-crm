import re

PROBE = "/api/_test/protected"


def _normalise(rule: str) -> str:
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def test_every_api_route_is_in_the_openapi_document(app):
    paths = app.api_doc["paths"]
    missing = []
    checked: set[tuple[str, str]] = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/") or rule.rule == PROBE:
            continue
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}:
            checked.add((method, _normalise(rule.rule)))
            if method.lower() not in paths.get(_normalise(rule.rule), {}):
                missing.append(f"{method} {rule.rule}")
    assert not missing, f"routes absent from OpenAPI document: {sorted(missing)}"
    assert len(checked) >= 40, f"only {len(checked)} routes checked"
    assert {("GET", "/api/patients"), ("POST", "/api/patients"), ("GET", "/api/patients/{patient_id}")} <= checked


def test_session_and_staff_management_use_distinct_staff_schemas(app):
    schemas = app.api_doc["components"]["schemas"]
    session_ref = schemas["MeResponse"]["properties"]["staff"]["$ref"]
    session_schema = schemas[session_ref.rsplit("/", 1)[-1]]
    assert set(session_schema["properties"]) == {"id", "full_name", "roles"}
    assert {"email", "clinics", "is_active"} <= set(schemas["StaffOut"]["properties"])
