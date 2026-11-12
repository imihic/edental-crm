import argparse
import base64
import csv
import getpass
from email.headerregistry import Address
import http.cookiejar
import io
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

import pyotp


def synthetic_email(label: str, run_id: str) -> str:
    return Address(username=f"{label}-{run_id}", domain="example.test").addr_spec


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method: str, path: str, body: dict | None = None, csrf: bool = True) -> tuple[int, dict]:
        headers = {}
        data = None
        if method != "GET":
            headers["Content-Type"] = "application/json"
            data = json.dumps(body or {}).encode()
            if csrf:
                headers["X-CSRF-Token"] = self.call("GET", "/api/auth/csrf")[1]["csrf_token"]
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def expect(
        self, label: str, status: int, method: str, path: str, body: dict | None = None, *, csrf: bool = True
    ) -> dict:
        actual, result = self.call(method, path, body, csrf=csrf)
        detail = f"HTTP {actual}"
        if actual != status and result.get("error"):
            detail += f" ({result['error']})"
        check(label, actual == status, detail)
        return result


def check(label: str, cond: bool, detail: object = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail != "" else ""))
    if not cond:
        sys.exit(1)


def make_oib(seed: str) -> str:
    digits = [int(ch) for ch in f"{int(seed, 16) % 10**10:010d}"]
    remainder = 10
    for digit in digits:
        remainder = (remainder + digit) % 10 or 10
        remainder = remainder * 2 % 11
    return "".join(map(str, digits)) + str((11 - remainder) % 10)


def smoke_import_payload(run_id: str) -> dict[str, str]:
    template = Path(__file__).resolve().parents[1] / "docs" / "patient-import-template.csv"
    with template.open(encoding="utf-8-sig", newline="") as source:
        (row,) = csv.DictReader(source, delimiter=";")
    row["Last name"] = f"{row['Last name']} {run_id}"
    row["Email"] = synthetic_email("import", run_id)
    row["OIB"] = make_oib(run_id[::-1])
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(row), delimiter=";")
    writer.writeheader()
    writer.writerow(row)
    return {"filename": template.name, "content_base64": base64.b64encode(output.getvalue().encode()).decode("ascii")}


def people_manager(c: Client, email: str, password: str, organization: str) -> dict:
    login = c.expect("manager login", 200, "POST", "/api/auth/login", {"email": email, "password": password})
    check("manager has already enrolled TOTP", login.get("status") == "totp_required")
    secret = os.getenv("SMOKE_TOTP_SECRET")
    code = pyotp.TOTP(secret).now() if secret else getpass.getpass("Manager TOTP code: ").strip()
    signed_in = c.expect("verify manager TOTP", 200, "POST", "/api/auth/totp", {"code": code})
    if signed_in.get("status") == "choose_organization":
        orgs = {org["name"]: org["id"] for org in signed_in["organizations"]}
        check("target Organization listed", organization in orgs, organization)
        c.expect(
            "choose target Organization", 200, "POST", "/api/auth/organization", {"organization_id": orgs[organization]}
        )
    me = c.expect("get manager session", 200, "GET", "/api/auth/me")
    check(
        "manager in target Organization",
        me["organization"]["name"] == organization and "clinic_manager" in me["staff"]["roles"],
    )
    check("manager has a Clinic", bool(me["clinics"]))
    return me


def people_smoke(c: Client, email: str, password: str, organization: str) -> None:
    manager = people_manager(c, email, password, organization)
    clinic_id = manager["clinics"][0]["id"]
    run_id = uuid4().hex
    smoke_name = f"Smoke {run_id}"

    patient = {"first_name": "Test Child", "last_name": smoke_name, "email": synthetic_email("patient", run_id),
               "oib": make_oib(run_id)}
    created = c.expect("create Patient", 201, "POST", "/api/patients", patient)
    patient_path = f"/api/patients/{created['id']}"
    guardian = c.expect("add Guardian", 201, "POST", f"{patient_path}/guardians", {
        "relationship": "parent", "contact": {"full_name": f"Test Guardian {smoke_name}"},
    })
    check("Guardian is a Contact", guardian["kind"] == "contact")
    consent = c.expect("record Consent", 201, "POST", f"{patient_path}/consents", {
        "purpose": "marketing", "granted": True, "source": "verbal", "given_by_guardian_link_id": guardian["id"],
    })
    check("Consent recorded from Guardian", consent["granted"] and consent["given_by_guardian_link_id"] == guardian["id"])

    lead_email = synthetic_email("lead", run_id)
    lead = c.expect("create Lead by phone", 201, "POST", "/api/leads", {
        "clinic_id": clinic_id, "source": "phone", "full_name": f"Test Lead {smoke_name}",
        "phone": "+12025550100", "email": lead_email, "message": "Synthetic phone enquiry",
    })
    check("Enquiry created a Lead", lead["attached_to"] == "lead" and bool(lead["lead_id"]))
    lead_path = f"/api/leads/{lead['lead_id']}"
    moved = c.expect("move Lead stage", 200, "POST", f"{lead_path}/stage", {"stage": "contacted"})
    check("Lead is contacted", moved["stage"] == "contacted")
    converted = c.expect("convert Lead", 201, "POST", f"{lead_path}/convert", {
        "first_name": "Test Lead", "last_name": smoke_name, "email": lead_email,
    })
    lead_detail = c.expect("get converted Lead", 200, "GET", lead_path)
    check(
        "Lead converted to new Patient",
        lead_detail["stage"] == "converted" and lead_detail["converted_patient_id"] == converted["id"],
    )

    twin = {key: value for key, value in patient.items() if key != "oib"}
    warning = c.expect("detect duplicate Patient", 409, "POST", "/api/patients", twin)
    check(
        "duplicate is the smoke Patient",
        warning.get("error") == "possible_duplicates"
        and any(candidate["id"] == created["id"] for candidate in warning["duplicates"]),
    )
    duplicate = c.expect(
        "confirm duplicate Patient", 201, "POST", "/api/patients", {**twin, "confirm_duplicates": True}
    )
    c.expect("merge duplicate Patient", 200, "POST", f"{patient_path}/merge", {
        "retired_kind": "patient", "retired_id": duplicate["id"],
    })
    retired = c.expect("get retired Patient", 410, "GET", f"/api/patients/{duplicate['id']}")
    check("duplicate retired into original Patient", retired.get("merged_into") == created["id"])

    import_path = "/api/imports/patients"
    preview = c.expect("preview Patient CSV", 200, "POST", f"{import_path}/preview", smoke_import_payload(run_id))
    check(
        "preview contains one valid row",
        preview["counts"] == {"total": 1, "valid": 1, "invalid": 0, "duplicate": 0},
        preview["counts"],
    )
    committed = c.expect("commit Patient CSV", 200, "POST", f"{import_path}/{preview['import_id']}/commit")
    check("one Patient imported", committed == {"created": 1, "skipped": 0}, committed)

    form_path = f"/api/clinics/{clinic_id}/enquiry-form"
    form = c.expect("get Enquiry Form key", 200, "GET", form_path)
    rotated = c.expect("regenerate Enquiry Form key", 200, "POST", f"{form_path}/regenerate")
    public = Client(c.base)
    public_forms = "/api/public/enquiry-forms"
    public.expect("old Enquiry Form key rejected", 404, "GET", f"{public_forms}/{form['key']}")
    enquiry_email = synthetic_email("enquiry", run_id)
    public.expect("submit public Enquiry", 202, "POST", f"{public_forms}/{rotated['key']}/enquiries", {
        "full_name": f"Test Enquiry {smoke_name}", "email": enquiry_email,
        "message": "Synthetic website enquiry", "marketing_consent": False,
    }, csrf=False)
    query = urlencode({"q": enquiry_email, "clinic_id": clinic_id})
    leads = c.expect("find public Enquiry Lead", 200, "GET", f"/api/leads?{query}")
    check("public Enquiry created a Lead", any(item["email"] == enquiry_email for item in leads["items"]))

    receptionist_email = synthetic_email("receptionist", run_id)
    invitation = c.expect("invite receptionist", 201, "POST", "/api/invitations", {
        "email": receptionist_email, "full_name": f"Test Receptionist {smoke_name}",
        "roles": ["receptionist"], "clinic_ids": [clinic_id],
    })
    token = urlparse(invitation["url"]).path.rsplit("/", 1)[-1]
    receptionist_password = secrets.token_urlsafe(24)
    public.expect("accept Invitation", 200, "POST", f"/api/public/invitations/{token}/accept", {
        "password": receptionist_password,
    }, csrf=False)
    public.expect("sign in as receptionist", 200, "POST", "/api/auth/login", {
        "email": receptionist_email, "password": receptionist_password,
    })
    receptionist = public.expect("get receptionist session", 200, "GET", "/api/auth/me")
    check(
        "receptionist in target Organization",
        receptionist["staff"]["roles"] == ["receptionist"]
        and receptionist["organization"]["id"] == manager["organization"]["id"],
    )
    denied = public.expect("receptionist denied GET /api/staff", 403, "GET", "/api/staff")
    check("staff access forbidden by role", denied.get("error") == "forbidden")
    public.expect("receptionist logout", 204, "POST", "/api/auth/logout")
    c.expect("manager logout", 204, "POST", "/api/auth/logout")
    print("SMOKE OK")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("email")
    ap.add_argument("password")
    ap.add_argument("--first", default="Smile", help="Organization for initial sign-in and the People smoke")
    ap.add_argument("--second", default="Beta", help="Organization to switch to")
    ap.add_argument("--people", action="store_true", help="Exercise People APIs in a disposable Clinic")
    a = ap.parse_args()
    c = Client(a.base_url)
    if a.people:
        people_smoke(c, a.email, a.password, a.first)
        return

    s, r = c.call("POST", "/api/auth/login", {"email": a.email, "password": a.password})
    check("login -> choose_organization", s == 200 and r.get("status") == "choose_organization", r.get("status"))
    orgs = {o["name"]: o["id"] for o in r["organizations"]}
    check("organizations listed", {a.first, a.second} <= set(orgs), sorted(orgs))
    s, r = c.call("GET", "/api/auth/organizations")
    check("GET organizations matches", s == 200 and {o["name"] for o in r["organizations"]} == set(orgs))

    s, r = c.call("POST", "/api/auth/organization", {"organization_id": orgs[a.first]})
    check(f"choose {a.first}", s == 200 and r.get("status") == "ok", s)
    s, r = c.call("GET", "/api/auth/me")
    check("me: totp_enrollment_required", s == 200 and r["totp_enrollment_required"] is True, r.get("organization", {}).get("name"))

    s, r = c.call("POST", "/api/auth/totp/enroll")
    check("enroll", s == 200 and "otpauth_uri" in r, s)
    secret = parse_qs(urlparse(r["otpauth_uri"]).query)["secret"][0]
    totp = pyotp.TOTP(secret)
    s, r = c.call("POST", "/api/auth/totp/confirm", {"code": totp.now()})
    check("confirm", s == 200 and r.get("status") == "ok", s)

    s, r = c.call("GET", "/api/auth/me")
    check(
        f"me: {a.first} + clinics",
        s == 200 and r["organization"]["name"] == a.first and len(r["clinics"]) >= 1 and not r["totp_enrollment_required"],
        [cl["name"] for cl in r.get("clinics", [])],
    )

    s, r = c.call("POST", "/api/auth/organization", {"organization_id": orgs[a.second]})
    check(f"switch to {a.second}", s == 200, s)
    s, r = c.call("GET", "/api/auth/me")
    check(f"me: {a.second}", s == 200 and r["organization"]["name"] == a.second, [cl["name"] for cl in r.get("clinics", [])])

    s, r = c.call("POST", "/api/auth/logout")
    check("logout", s in (200, 204), s)
    s, _ = c.call("GET", "/api/auth/me")
    check("me after logout -> 401", s == 401, s)

    s, r = c.call("POST", "/api/auth/login", {"email": a.email, "password": a.password})
    check("login again -> totp_required", s == 200 and r.get("status") == "totp_required", r.get("status"))
    s, r = c.call("POST", "/api/auth/totp", {"code": totp.now()})
    check("verify totp -> choose_organization", s == 200 and r.get("status") in ("ok", "choose_organization"), r.get("status"))
    if r.get("status") == "choose_organization":
        s, r = c.call("POST", "/api/auth/organization", {"organization_id": orgs[a.first]})
        check(f"choose {a.first}", s == 200, s)
    s, r = c.call("GET", "/api/auth/me")
    check("me after second sign-in", s == 200 and r["organization"]["name"] == a.first)
    s, r = c.call("POST", "/api/auth/logout")
    check("final logout", s in (200, 204), s)
    print("SMOKE OK")


if __name__ == "__main__":
    main()
