"""Google Health authorization: staff link -> consent -> Google record (10.1-05).

GHA-01 and the supersede half of GHA-06. The flow runs end to end against
fakes (see ``google_health_harness``): a staff member mints a
participant-bound link, the participant's browser follows it to Google with a
signed, browser-bound ``state``, and ``finishAuth`` stores one
``provider: googleHealth`` record, supersedes every other active record of the
participant, and publishes ``googleHealth.completeMigration`` onto
``scheduler_new``. Contract: opserver ``docs/google-health.md``.
"""

from __future__ import annotations

import base64
import hashlib
import urllib.parse
from datetime import UTC, datetime

import jwt
import pytest
import time_machine
from bson import ObjectId

from .google_health_harness import (
    AUTHORIZE_PATH,
    FULL_SCOPE,
    PUBLIC_BASE_URL,
    Harness,
    set_cookie_header,
)

FROZEN = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
FROZEN_TS = int(FROZEN.timestamp())
SCOPES = FULL_SCOPE.split(" ")


@pytest.fixture
def h() -> Harness:
    return Harness()


def _decode_state(h: Harness, state: str) -> dict:
    return jwt.decode(
        state,
        h.settings.state_secret,
        algorithms=["HS256"],
        audience="googleHealth:state",
        issuer="openwellness-api",
    )


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --- Task 1: the happy path ---------------------------------------------------


def test_admin_mints_a_participant_link(h: Harness) -> None:
    pid = h.seed_participant()
    with time_machine.travel(FROZEN, tick=False):
        resp = h.client().post("/api/googleHealth/links", json={"participantId": pid})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"url", "expiresAt"}
    assert body["url"].startswith(f"{PUBLIC_BASE_URL}{AUTHORIZE_PATH}?t=")
    assert isinstance(body["expiresAt"], int)
    assert body["expiresAt"] == FROZEN_TS + 72 * 3600


def test_authorize_redirects_to_google_with_a_browser_bound_state(h: Harness) -> None:
    pid = h.seed_participant()
    client = h.client()
    with time_machine.travel(FROZEN, tick=False):
        url = h.mint_link(client, pid)
        resp, state, cookie = h.authorize(client, url)
        claims = _decode_state(h, state)

    location = urllib.parse.urlsplit(resp.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    query = urllib.parse.parse_qs(location.query)
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["client_id"] == [h.settings.client_id]
    assert query["redirect_uri"] == [f"{PUBLIC_BASE_URL}/api/googleHealth/finishAuth"]
    assert query["scope"][0].split(" ") == SCOPES
    assert len(SCOPES) == 4

    assert claims["aud"] == "googleHealth:state"
    assert claims["sub"] == pid
    assert claims["exp"] == FROZEN_TS + 900
    assert claims["bh"] == _b64url_sha256(cookie)

    header = set_cookie_header(resp)
    attributes = {part.strip().split("=", 1)[0].lower() for part in header.split(";")[1:]}
    assert {"httponly", "secure", "samesite", "path", "max-age"} <= attributes
    assert "samesite=lax" in header.lower()
    assert "path=/api/googlehealth" in header.lower()
    assert "max-age=900" in header.lower()
    assert len(base64.urlsafe_b64decode(cookie + "=" * (-len(cookie) % 4))) == 32

    ttl = h.redis.ttl(f"gh:state:{claims['jti']}")
    assert 0 < ttl <= 900


def test_finish_auth_stores_the_google_record_supersedes_legacy_and_publishes(
    h: Harness,
) -> None:
    pid = h.seed_participant()
    legacy_id = h.seed_legacy(pid)
    h.google.add(
        "code-1",
        access="g-access-1",
        refresh="g-refresh-1",
        health_user_id="HUSER1",
        legacy_user_id="LEGACYOWNER1",
    )

    with time_machine.travel(FROZEN, tick=False):
        resp = h.run_flow(pid, "code-1")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")

    (record,) = h.google_records()
    google_id = str(record["_id"])
    assert set(record) == {
        "_id",
        "participantId",
        "provider",
        "accessToken",
        "refreshToken",
        "expiresAt",
        "scope",
        "healthUserId",
        "legacyUserId",
        "timeCreated",
        "migratedAt",
        "migrationStatus",
    }
    assert record["participantId"] == pid
    assert record["provider"] == "googleHealth"
    assert record["accessToken"] == "g-access-1"
    assert record["refreshToken"] == "g-refresh-1"
    assert record["expiresAt"] == FROZEN_TS + 3599
    assert record["scope"] == FULL_SCOPE
    assert record["healthUserId"] == "HUSER1"
    assert record["legacyUserId"] == "LEGACYOWNER1"
    assert record["timeCreated"] == FROZEN_TS
    assert record["migratedAt"] == FROZEN_TS
    assert record["migrationStatus"] == "pending"

    legacy = h.db["fitbits"].find_one({"_id": ObjectId(legacy_id)})
    assert legacy is not None
    assert legacy["supersededAt"] == FROZEN_TS
    assert legacy["supersededBy"] == google_id
    assert "ownerId" not in record

    assert h.publisher.calls == [
        ("googleHealth.completeMigration", [pid, google_id, [legacy_id]], "scheduler_new")
    ]
    assert h.google.exchanges == ["code-1"]


def test_reconsent_carries_the_first_migration_date_forward(h: Harness) -> None:
    pid = h.seed_participant()
    first = FROZEN_TS - 30 * 86400
    older_id = h.seed_google(pid, health_user_id="HUSER1", migrated_at=first)
    h.google.add(
        "code-2",
        access="g-access-2",
        refresh="g-refresh-2",
        health_user_id="HUSER1",
        legacy_user_id=None,
    )

    with time_machine.travel(FROZEN, tick=False):
        resp = h.run_flow(pid, "code-2")

    assert resp.status_code == 200, resp.text
    (active,) = h.active_google()
    assert str(active["_id"]) != older_id
    assert active["migratedAt"] == first
    assert active["timeCreated"] == FROZEN_TS
    older = h.db["fitbits"].find_one({"_id": ObjectId(older_id)})
    assert older is not None
    assert older["supersededAt"] == FROZEN_TS
    assert older["supersededBy"] == str(active["_id"])
    assert h.publisher.calls == [
        ("googleHealth.completeMigration", [pid, str(active["_id"]), [older_id]], "scheduler_new")
    ]
