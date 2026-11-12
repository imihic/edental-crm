from testing import fake_email

import json
import logging
import re


def test_request_id_is_echoed_or_generated(client):
    r = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["X-Request-ID"] == "abc-123"
    r = client.get("/api/health", headers={"X-Request-ID": "bad id!"})
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["X-Request-ID"])


def test_log_lines_are_json_with_request_id(app, client, capsys):
    @app.get("/logme")
    def logme():
        logging.getLogger("test.logme").warning("hello")
        return {"ok": True}

    r = client.get("/logme", headers={"X-Request-ID": "req-1"})
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    records = [json.loads(ln) for ln in lines]
    rec = next(x for x in records if x["message"] == "hello")
    assert rec["request_id"] == r.headers["X-Request-ID"] == "req-1"
    assert rec["level"] == "WARNING"
    assert rec["logger"] == "test.logme"
    assert rec["organization_id"] is None and rec["staff_member_id"] is None
    assert "ts" in rec


def test_exception_text_is_not_logged_but_type_is(app, client, capsys):
    @app.get("/pii")
    def pii():
        raise ValueError(fake_email('testa', 'clinic.example.test'))

    client.get("/pii")
    out = capsys.readouterr().out
    assert fake_email('testa', 'clinic.example.test') not in out
    assert "ValueError" in out
