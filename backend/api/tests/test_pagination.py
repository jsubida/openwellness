"""Pagination round-trip and page-size capping."""

from openwellness_api.common.pagination import (
    MAX_PAGE_SIZE,
    PageParams,
    _decode_token,
    _encode_token,
    paginate,
)


def test_token_round_trip() -> None:
    token = _encode_token(125)
    assert _decode_token(token) == 125


def test_paginate_emits_token_only_when_more_remain() -> None:
    items = list(range(10))

    page1, t1 = paginate(items, PageParams(page_size=4, offset=0))
    assert page1 == [0, 1, 2, 3]
    assert t1 is not None
    assert _decode_token(t1) == 4

    page2, t2 = paginate(items, PageParams(page_size=4, offset=4))
    assert page2 == [4, 5, 6, 7]
    assert t2 is not None
    assert _decode_token(t2) == 8

    page3, t3 = paginate(items, PageParams(page_size=4, offset=8))
    assert page3 == [8, 9]
    assert t3 is None  # end of list


def test_listing_uses_page_params(client) -> None:
    # Create 5 users.
    for i in range(5):
        client.post(
            "/v1/users",
            json={"email": f"u{i}@x.com", "isActive": True, "username": f"u{i}"},
        )
    r = client.get("/v1/users", params={"page_size": 2})
    body = r.json()
    assert len(body["users"]) == 2
    assert body["nextPageToken"] is not None

    r2 = client.get(
        "/v1/users",
        params={"page_size": 2, "page_token": body["nextPageToken"]},
    )
    body2 = r2.json()
    assert len(body2["users"]) == 2
    assert body2["nextPageToken"] is not None

    r3 = client.get(
        "/v1/users",
        params={"page_size": 2, "page_token": body2["nextPageToken"]},
    )
    body3 = r3.json()
    assert len(body3["users"]) == 1
    assert body3["nextPageToken"] is None


def test_page_size_capped(client) -> None:
    r = client.get("/v1/users", params={"page_size": MAX_PAGE_SIZE + 1})
    # The request-validation handler rewrites FastAPI's 422 into a
    # AIP-193-style 400 INVALID_ARGUMENT.
    assert r.status_code == 400
    assert r.json()["error"]["status"] == "INVALID_ARGUMENT"


def test_invalid_page_token_rejected(client) -> None:
    r = client.get("/v1/users", params={"page_token": "not-base64-json"})
    assert r.status_code == 400
