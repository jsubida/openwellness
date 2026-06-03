"""Happy-path CRUD for the top-level Users resource (AIP wire format)."""


def test_user_crud_flow(client) -> None:
    # Create
    payload = {
        "email": "a@b.com",
        "isActive": True,
        "username": "alice",
    }
    r = client.post("/v1/users", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    name = created["name"]
    assert name.startswith("users/")
    user_id = name.split("/", 1)[1]
    assert created["email"] == "a@b.com"
    # User is a BaseEntity (no audit timestamps); createTime is absent/null.

    # Get
    r = client.get(f"/v1/users/{user_id}")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert r.json()["name"] == name

    # Patch — only changed field
    r = client.patch(f"/v1/users/{user_id}", json={"location": "NY"})
    assert r.status_code == 200
    assert r.json()["location"] == "NY"
    assert r.json()["username"] == "alice"  # unchanged

    # List — items field is the resource plural per AIP-132
    r = client.get("/v1/users", params={"page_size": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body["users"]) == 1
    assert body["nextPageToken"] is None

    # Archive (soft delete)
    r = client.delete(f"/v1/users/{user_id}")
    assert r.status_code == 204
    # Still retrievable; archive copies, doesn't move.
    r = client.get(f"/v1/users/{user_id}")
    assert r.status_code == 200

    # Undelete (no-op for in-memory fake; round-trips the entity)
    r = client.post(f"/v1/users/{user_id}:undelete")
    assert r.status_code == 200
    assert r.json()["name"] == name

    # Purge (hard delete)
    r = client.post(f"/v1/users/{user_id}:purge")
    assert r.status_code == 204
    r = client.get(f"/v1/users/{user_id}")
    assert r.status_code == 404


def test_user_404_envelope(client) -> None:
    r = client.get("/v1/users/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["status"] == "NOT_FOUND"
    assert body["error"]["code"] == 404
