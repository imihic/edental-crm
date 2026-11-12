from testing import fake_email, fake_password

def test_csrf_token_is_created_once_per_session(client):
    first = client.get("/api/auth/csrf").get_json()["csrf_token"]
    assert isinstance(first, str) and len(first) >= 32
    assert client.get("/api/auth/csrf").get_json()["csrf_token"] == first


def test_csrf_token_rotates_with_authentication(client, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    before = csrf(client)
    client.post("/api/auth/login", json={"email": fake_email('testa', 'clinic.example.test'), "password": fake_password('account')})
    after = csrf(client)
    assert before != after
    r = client.post("/api/auth/logout", json={}, headers=before)
    assert (r.status_code, r.get_json()) == (403, {"error": "csrf_failed"})


def test_non_json_mutation_rejected_even_without_body(client):
    r = client.post("/api/auth/logout")
    assert (r.status_code, r.get_json()) == (415, {"error": "json_required"})
