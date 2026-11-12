from testing import fake_email

from app.identity import Role
from app.identity.guards import login_required, require_role
from app.identity.session import current_staff


def test_login_required_and_require_role(app, client, login, make_org, make_staff):
    @app.get("/t/any")
    @login_required
    def any_staff():
        return {"id": str(current_staff().id)}

    @app.get("/t/manager")
    @require_role(Role.CLINIC_MANAGER, Role.DENTIST)
    def manager():
        return {"ok": True}

    assert client.get("/t/any").get_json() == {"error": "unauthenticated"}
    assert client.get("/t/manager").status_code == 401
    staff = make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'), roles=(Role.RECEPTIONIST,))
    login(client, fake_email('testa', 'clinic.example.test'))
    assert client.get("/t/any").get_json() == {"id": str(staff.id)}
    r = client.get("/t/manager")
    assert (r.status_code, r.get_json()) == (403, {"error": "forbidden"})


def test_require_role_passes_on_any_held_role(app, client, login, make_org, make_staff):
    @app.get("/t/manager")
    @require_role(Role.CLINIC_MANAGER)
    def manager():
        return {"ok": True}

    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'), roles=(Role.DENTIST, Role.CLINIC_MANAGER))
    login(client, fake_email('testa', 'clinic.example.test'))
    assert client.get("/t/manager").get_json() == {"ok": True}


def test_identity_root_exports_route_guards():
    import app.identity as identity

    for name in ("login_required", "require_role", "current_staff", "current_account_id", "Role"):
        assert name in identity.__all__ and hasattr(identity, name), name
