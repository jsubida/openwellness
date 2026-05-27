"""Round-trip the Goal discriminated union + AIP-160 ``filter=kind=N``."""


def test_create_weekly_and_daily_goals(client) -> None:
    headers = {"X-Principal-Id": "tester"}

    r = client.post(
        "/v1/users/u-1/goals",
        json={"kind": 0, "startDate": 1.0},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    weekly = r.json()
    assert weekly["owner"] == "u-1"
    assert weekly["name"].startswith("users/u-1/goals/")

    r = client.post(
        "/v1/users/u-1/goals",
        json={"kind": 1, "startDate": 2.0},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    daily = r.json()

    r = client.post(
        "/v1/users/u-1/goals",
        json={"kind": 2, "weight": 150.0, "calories": 1800.0},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    legacy = r.json()
    assert legacy["owner"] == "u-1"

    # List all
    r = client.get("/v1/users/u-1/goals")
    assert r.status_code == 200
    assert len(r.json()["goals"]) == 3

    # Filter by kind=1 (daily) using AIP-160 ``filter=`` syntax.
    r = client.get("/v1/users/u-1/goals", params={"filter": "kind=1"})
    assert r.status_code == 200
    goals = r.json()["goals"]
    assert len(goals) == 1
    assert goals[0]["name"] == daily["name"]


def test_filter_rejects_unknown_field(client) -> None:
    headers = {"X-Principal-Id": "tester"}
    client.post(
        "/v1/users/u-2/goals",
        json={"kind": 0, "startDate": 1.0},
        headers=headers,
    )
    r = client.get("/v1/users/u-2/goals", params={"filter": "weight=10"})
    assert r.status_code == 400
    assert r.json()["error"]["status"] == "INVALID_ARGUMENT"


def test_filter_rejects_unsupported_operator(client) -> None:
    r = client.get("/v1/users/u-3/goals", params={"filter": "kind>1"})
    assert r.status_code == 400
    assert r.json()["error"]["status"] == "INVALID_ARGUMENT"
