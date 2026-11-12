def test_lists_imports_newest_first_for_managers_only(client, manager_in, upload):
    _org, _staff, headers = manager_in
    assert client.get("/api/imports").get_json() == {"items": []}
    a = upload(headers, "ime;prezime\nTesta;Testić\n", "a.csv").get_json()["import_id"]
    b = upload(headers, "ime;prezime\nTestiva;Testnovak\nTesto;Testnovak\n", "b.csv").get_json()["import_id"]
    client.post(f"/api/imports/patients/{a}/commit", json={"include_duplicates": False}, headers=headers)
    items = client.get("/api/imports").get_json()["items"]
    assert [i["id"] for i in items] == [b, a]
    assert items[0]["filename"] == "b.csv" and items[0]["status"] == "previewed"
    assert items[0]["counts"] == {"total": 2, "valid": 2, "invalid": 0, "duplicate": 0}
    assert items[1]["status"] == "committed" and items[1]["committed_at"] is not None
    assert items[1]["counts"] == {"created": 1, "skipped": 0}
    assert "rows" not in items[0]


def test_receptionist_cannot_list(client, signed_in):
    assert client.get("/api/imports").status_code == 403
