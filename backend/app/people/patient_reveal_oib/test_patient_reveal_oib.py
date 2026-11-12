OIB = "11111111119"


def test_reveal_oib_is_audited_without_the_value_in_detail(client, signed_in, make_patient, audit_rows):
    p = make_patient(signed_in[0], oib=OIB)
    r = client.post(f"/api/patients/{p.id}/reveal-oib", json={}, headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (200, {"oib": OIB})
    [e] = audit_rows()
    assert (e.action, e.entity_id, e.detail) == ("view", p.id, {"field": "oib"})
    assert OIB not in str(e.detail)


def test_reveal_oib_when_absent_and_other_org(client, signed_in, make_patient, make_org):
    p = make_patient(signed_in[0])
    r = client.post(f"/api/patients/{p.id}/reveal-oib", json={}, headers=signed_in[2])
    assert r.get_json() == {"oib": None}
    other = make_patient(make_org("Other"), oib=OIB)
    assert client.post(f"/api/patients/{other.id}/reveal-oib", json={}, headers=signed_in[2]).status_code == 404
