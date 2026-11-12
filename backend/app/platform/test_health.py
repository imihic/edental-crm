from app.platform.errors import ApiError


def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


def test_unknown_route_returns_json_error(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.get_json() == {"error": "not_found"}


def test_wrong_method_returns_json_error(client):
    r = client.post("/api/health")
    assert r.status_code == 405
    assert r.get_json() == {"error": "method_not_allowed"}
    assert "GET" in r.headers["Allow"]
    assert r.headers["Content-Type"] == "application/json"


def test_api_error_and_500_do_not_leak(app):
    app.config["PROPAGATE_EXCEPTIONS"] = False

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret detail")

    @app.get("/teapot")
    def teapot():
        raise ApiError(418, "teapot")

    c = app.test_client()
    r = c.get("/boom")
    assert r.status_code == 500
    assert r.get_json() == {"error": "internal_error"}
    assert b"secret detail" not in r.data and b"Traceback" not in r.data
    r = c.get("/teapot")
    assert (r.status_code, r.get_json()) == (418, {"error": "teapot"})
