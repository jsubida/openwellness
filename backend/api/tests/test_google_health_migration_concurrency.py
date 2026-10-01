"""Google Health migration: concurrency, the migration hold and partial failures.

10.1-05 Task 3 (review round 1, P0; contract invariants I1-I3, I5;
T-10.1-74). finishAuth takes the link claim ``gh:link:claim:<jti>`` before
the code exchange, then the participant lock ``gh:lock:pid:<P>`` and the
account lock ``gh:lock:hu:<sha256(H)[:32]>``, rechecks that no other
participant holds the Google account, inserts the record ``pending``,
supersedes, releases the locks and publishes. So:

- no interleaving of links, states, participants or Google accounts yields
  two active Google records for a participant or an account;
- every failure before the insert writes nothing and gives the link back;
- an insert whose outcome is unknown keeps the link consumed;
- every failure after the insert leaves a ``pending`` record the scheduler's
  reconcile re-drives;
- the locks are released on every path.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import threading
from collections.abc import Callable
from typing import Any

import pytest
from pymongo.errors import AutoReconnect, WriteError
from redis.exceptions import ConnectionError as RedisConnectionError

from openwellness_api.google_health.oauth import BUSY_PAGE, ERROR_PAGE, SUCCESS_PAGE
from openwellness_api.google_health.store import GoogleHealthStore
from openwellness_api.google_health.tokens import GoogleHealthTokens

from .google_health_harness import LINKS_PATH, Harness


@pytest.fixture
def h() -> Harness:
    return Harness()


def _lock_keys(h: Harness) -> list[str]:
    return sorted(h.redis.keys("gh:lock:*"))


def _claims(h: Harness) -> list[str]:
    return sorted(h.redis.keys("gh:link:claim:*"))


def _hu_key(health_user_id: str) -> str:
    return "gh:lock:hu:" + hashlib.sha256(health_user_id.encode()).hexdigest()[:32]


def _is_error(resp: Any) -> bool:
    return resp.status_code in (400, 500) and resp.text == ERROR_PAGE


def _is_busy(resp: Any) -> bool:
    return resp.status_code == 409 and resp.text == BUSY_PAGE


def _is_success(resp: Any) -> bool:
    return resp.status_code == 200 and resp.text == SUCCESS_PAGE


class HookedStore:
    """The real store with a hook run before chosen methods (raise or block)."""

    def __init__(self, inner: GoogleHealthStore, hooks: dict[str, Callable[[], None]]) -> None:
        self._inner = inner
        self._hooks = hooks

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        hook = self._hooks.get(name)
        if hook is None:
            return attr

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            hook()
            return attr(*args, **kwargs)

        return wrapped


class FaultyRedis:
    """fakeredis that raises a Redis error for chosen (operation, key prefix) pairs."""

    def __init__(self, inner: Any, fail: set[tuple[str, str]]) -> None:
        self._inner = inner
        self._fail = fail

    def _check(self, op: str, key: str) -> None:
        for fail_op, prefix in self._fail:
            if op == fail_op and key.startswith(prefix):
                raise RedisConnectionError("injected")

    def set(self, key: str, *args: Any, **kwargs: Any) -> Any:
        self._check("set", key)
        return self._inner.set(key, *args, **kwargs)

    def delete(self, *keys: str) -> Any:
        for key in keys:
            self._check("delete", key)
        return self._inner.delete(*keys)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _swap(h: Harness, **changes: Any) -> None:
    h.deps = dataclasses.replace(h.deps, **changes)
    h.app.state.google_health_deps = h.deps


def _raise() -> None:
    raise RuntimeError("injected mongo failure")


def _prepared(h: Harness, pid: str, code: str, *, health: str = "H1") -> tuple[Any, str, str]:
    """Mint and follow a link; return (client, state, cookie) ready to finish."""
    h.google.add(code, access=f"a-{code}", refresh=f"r-{code}", health_user_id=health, legacy_user_id=None)
    client = h.client()
    url = h.mint_link(client, pid)
    _, state, cookie = h.authorize(client, url)
    return client, state, cookie


# --- link claim ----------------------------------------------------------------


def test_two_states_from_one_link_exchange_the_code_once(h: Harness) -> None:
    pid = h.seed_participant()
    h.google.add("c1", access="a1", refresh="r1", health_user_id="H1", legacy_user_id=None)
    h.google.add("c2", access="a2", refresh="r2", health_user_id="H1", legacy_user_id=None)
    client = h.client()
    url = h.mint_link(client, pid)
    _, state1, cookie1 = h.authorize(client, url)
    _, state2, cookie2 = h.authorize(client, url)

    assert _is_success(h.finish(client, code="c1", state=state1, cookie=cookie1))
    second = h.finish(client, code="c2", state=state2, cookie=cookie2)

    assert _is_error(second)
    assert h.google.exchanges == ["c1"]
    assert len(h.google_records()) == 1
    assert len(h.publisher.calls) == 1
    assert _lock_keys(h) == []


def test_the_claim_outlives_the_insert_and_expires_with_the_link(h: Harness) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    assert _is_success(h.finish(client, code="c1", state=state, cookie=cookie))
    (claim,) = _claims(h)
    assert 0 < h.redis.ttl(claim) <= h.settings.link_ttl_seconds


# --- participant lock ----------------------------------------------------------


def test_two_links_for_one_participant_concurrently_yield_one_record(h: Harness) -> None:
    pid = h.seed_participant()
    legacy = h.seed_legacy(pid)
    client_a, state_a, cookie_a = _prepared(h, pid, "cA")
    url_b = h.mint_link(h.client(), pid)
    client_b = h.client()
    _, state_b, cookie_b = h.authorize(client_b, url_b)
    h.google.add("cB", access="a-cB", refresh="r-cB", health_user_id="H1", legacy_user_id=None)

    gate_a, gate_b = threading.Event(), threading.Event()
    h.google.identity_gate.update({"a-cA": gate_a, "a-cB": gate_b})
    b_entered = threading.Event()
    h.google.identity_entered["a-cB"] = b_entered
    a_in_insert, release_insert = threading.Event(), threading.Event()

    def hold_first_insert() -> None:
        if not a_in_insert.is_set():
            a_in_insert.set()
            assert release_insert.wait(timeout=10)

    _swap(h, store=HookedStore(h.deps.store, {"insert_google_record": hold_first_insert}))
    results: dict[str, Any] = {}

    def run(name: str, client: Any, code: str, state: str, cookie: str) -> None:
        results[name] = h.finish(client, code=code, state=state, cookie=cookie)

    ta = threading.Thread(target=run, args=("A", client_a, "cA", state_a, cookie_a))
    tb = threading.Thread(target=run, args=("B", client_b, "cB", state_b, cookie_b))
    ta.start()
    tb.start()
    assert b_entered.wait(timeout=10)
    gate_a.set()
    assert a_in_insert.wait(timeout=10)  # A holds both locks now
    gate_b.set()
    tb.join(timeout=10)
    release_insert.set()
    ta.join(timeout=10)

    assert _is_success(results["A"])
    assert _is_busy(results["B"])
    (active,) = h.active_google()
    assert h.publisher.calls == [
        ("googleHealth.completeMigration", [pid, str(active["_id"]), [legacy]], "scheduler_new")
    ]
    assert _lock_keys(h) == []
    # B's link was given back, so the participant can simply retry it.
    assert len(_claims(h)) == 1
    _, state_b2, cookie_b2 = h.authorize(client_b, url_b)
    h.google.identity_gate.clear()
    h.google.add("cB2", access="a-cB2", refresh="r-cB2", health_user_id="H1", legacy_user_id=None)
    assert _is_success(h.finish(client_b, code="cB2", state=state_b2, cookie=cookie_b2))
    assert len(h.active_google(participantId=pid)) == 1
    assert _lock_keys(h) == []


def test_a_held_participant_lock_answers_busy_and_gives_the_link_back(h: Harness) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    h.redis.set(f"gh:lock:pid:{pid}", "someone-else", px=60000)

    resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_busy(resp)
    assert h.google_records() == []
    assert _claims(h) == []
    assert h.redis.get(f"gh:lock:pid:{pid}") == "someone-else"
    assert h.redis.get(_hu_key("H1")) is None


# --- account uniqueness (I2) -----------------------------------------------------


def test_one_google_account_cannot_connect_a_second_participant(h: Harness) -> None:
    p1, p2 = h.seed_participant(), h.seed_participant()
    client1, s1, k1 = _prepared(h, p1, "c1", health="HSHARED")
    assert _is_success(h.finish(client1, code="c1", state=s1, cookie=k1))
    client2, s2, k2 = _prepared(h, p2, "c2", health="HSHARED")

    resp = h.finish(client2, code="c2", state=s2, cookie=k2)

    assert _is_error(resp)
    assert h.google_records(participantId=p2) == []
    assert len(h.active_google(healthUserId="HSHARED")) == 1
    assert h.google.revokes == []
    assert len(h.publisher.calls) == 1
    assert _lock_keys(h) == []


def test_one_google_account_on_two_participants_concurrently(h: Harness) -> None:
    p1, p2 = h.seed_participant(), h.seed_participant()
    client1, s1, k1 = _prepared(h, p1, "c1", health="HSHARED")
    client2, s2, k2 = _prepared(h, p2, "c2", health="HSHARED")
    gate = threading.Event()
    entered = {"a-c1": threading.Event(), "a-c2": threading.Event()}
    h.google.identity_entered.update(entered)
    h.google.identity_gate.update({"a-c1": gate, "a-c2": gate})
    results: list[Any] = []

    def run(client: Any, code: str, state: str, cookie: str) -> None:
        results.append(h.finish(client, code=code, state=state, cookie=cookie))

    threads = [
        threading.Thread(target=run, args=(client1, "c1", s1, k1)),
        threading.Thread(target=run, args=(client2, "c2", s2, k2)),
    ]
    for t in threads:
        t.start()
    assert all(e.wait(timeout=10) for e in entered.values())
    gate.set()
    for t in threads:
        t.join(timeout=10)

    assert sum(_is_success(r) for r in results) == 1
    assert sum(_is_busy(r) or _is_error(r) for r in results) == 1
    assert len(h.active_google(healthUserId="HSHARED")) == 1
    assert h.google.revokes == []
    assert _lock_keys(h) == []


# --- migration hold --------------------------------------------------------------


@pytest.mark.parametrize("hold", ["study", "*"])
def test_a_held_study_cannot_mint_a_link(
    h: Harness, hold: str, caplog: pytest.LogCaptureFixture
) -> None:
    pid = h.seed_participant()
    study = str(h.db["participants"].find_one()["studyId"])  # type: ignore[index]
    h.settings.migration_hold = study if hold == "study" else "*"

    with caplog.at_level(logging.WARNING):
        resp = h.client().post(LINKS_PATH, json={"participantId": pid})

    assert resp.status_code == 409
    assert pid not in resp.text and study not in resp.text
    assert "googleHealth/links held" in caplog.text
    assert pid not in caplog.text and study not in caplog.text


def test_a_participant_in_another_study_is_not_held(h: Harness) -> None:
    held = h.seed_participant()
    free = h.seed_participant()
    h.settings.migration_hold = str(h.db["participants"].find_one({"couchId": held})["studyId"])  # type: ignore[index]
    client, state, cookie = _prepared(h, free, "c1")
    assert _is_success(h.finish(client, code="c1", state=state, cookie=cookie))


def test_a_hold_placed_after_the_link_stops_authorize(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    pid = h.seed_participant()
    client = h.client()
    url = h.mint_link(client, pid)
    h.settings.migration_hold = "*"
    with caplog.at_level(logging.WARNING):
        resp = client.get("/api/googleHealth/authorize", params={"t": h.link_token(url)})
    assert _is_error(resp)
    assert "set-cookie" not in resp.headers
    assert h.redis.keys("gh:state:*") == []
    assert "googleHealth/authorize held" in caplog.text


def test_a_hold_placed_after_consent_began_stops_finish_auth(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    pid = h.seed_participant()
    h.seed_legacy(pid)
    client, state, cookie = _prepared(h, pid, "c1")
    h.settings.migration_hold = "*"
    with caplog.at_level(logging.WARNING):
        resp = h.finish(client, code="c1", state=state, cookie=cookie)
    assert _is_error(resp)
    assert h.google.exchanges == []
    assert h.google_records() == []
    assert h.db["fitbits"].count_documents({"supersededAt": {"$ne": None}}) == 0
    assert _claims(h) == []
    assert "googleHealth/finishAuth held" in caplog.text
    assert pid not in caplog.text


# --- failure injection, one step at a time ---------------------------------------


def _faulty_tokens(h: Harness, fail: set[tuple[str, str]]) -> None:
    _swap(h, tokens=GoogleHealthTokens(h.settings, FaultyRedis(h.redis, fail)))


def test_redis_error_consuming_the_nonce_writes_nothing(h: Harness) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    _faulty_tokens(h, {("delete", "gh:state:")})
    resp = h.finish(client, code="c1", state=state, cookie=cookie)
    assert _is_error(resp)
    assert h.google.exchanges == []
    assert h.google_records() == []
    assert _claims(h) == [] and _lock_keys(h) == []


def test_redis_error_claiming_the_link_exchanges_nothing(h: Harness) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    _faulty_tokens(h, {("set", "gh:link:claim:")})
    resp = h.finish(client, code="c1", state=state, cookie=cookie)
    assert _is_error(resp)
    assert h.google.exchanges == []
    assert h.google_records() == []
    assert _claims(h) == [] and _lock_keys(h) == []


@pytest.mark.parametrize("which", ["gh:lock:pid:", "gh:lock:hu:"])
def test_redis_error_taking_a_lock_answers_busy_and_gives_the_link_back(
    h: Harness, which: str
) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    _faulty_tokens(h, {("set", which)})
    resp = h.finish(client, code="c1", state=state, cookie=cookie)
    assert _is_busy(resp)
    assert h.google_records() == []
    assert h.publisher.calls == []
    assert _claims(h) == [] and _lock_keys(h) == []


@pytest.mark.parametrize(
    "step",
    ["participant", "active_google_owner_of", "legacy_owner_ids", "carried_migrated_at", "insert_google_record"],
)
def test_mongo_error_before_the_insert_writes_nothing_and_gives_the_link_back(
    h: Harness, step: str
) -> None:
    pid = h.seed_participant()
    legacy = h.seed_legacy(pid)
    client, state, cookie = _prepared(h, pid, "c1")
    if step == "participant":

        class BrokenParticipants:
            def find_by_id(self, participant_id: object) -> dict[str, Any] | None:
                raise RuntimeError("injected mongo failure")

            def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
                raise RuntimeError("injected mongo failure")

        _swap(h, participants=BrokenParticipants())
    elif step == "insert_google_record":

        def refused() -> None:
            # The server answered: nothing was written.
            raise WriteError("injected write error", code=121)

        _swap(h, store=HookedStore(h.deps.store, {step: refused}))
    else:
        _swap(h, store=HookedStore(h.deps.store, {step: _raise}))

    resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_error(resp)
    assert h.google_records() == []
    assert h.db["fitbits"].find_one({"supersededAt": {"$ne": None}}) is None
    assert h.db["fitbits"].count_documents({}) == 1 and legacy
    assert h.publisher.calls == []
    assert _claims(h) == [] and _lock_keys(h) == []


@pytest.mark.parametrize("error", [AutoReconnect("injected"), RuntimeError("injected")])
def test_an_insert_with_an_unknown_outcome_keeps_the_link_consumed(
    h: Harness, error: Exception
) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")

    def ambiguous() -> None:
        raise error

    _swap(h, store=HookedStore(h.deps.store, {"insert_google_record": ambiguous}))
    resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_error(resp) and resp.status_code == 500
    assert h.publisher.calls == []
    # The insert may have committed: a retry with the same link must not
    # write a second record.
    (claim,) = _claims(h)
    assert h.redis.ttl(claim) > h.settings.lock_ttl_ms // 1000
    assert _lock_keys(h) == []


def test_mongo_error_superseding_after_the_insert_still_publishes(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    pid = h.seed_participant()
    h.seed_legacy(pid)
    client, state, cookie = _prepared(h, pid, "c1")
    _swap(h, store=HookedStore(h.deps.store, {"supersede_active": _raise}))

    with caplog.at_level(logging.ERROR):
        resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_success(resp)
    (record,) = h.google_records()
    assert record["migrationStatus"] == "pending"
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors == ["googleHealth/finishAuth supersede failed: RuntimeError"]
    # The scheduler's completeMigration re-supersedes; publish is still attempted.
    assert h.publisher.calls == [
        ("googleHealth.completeMigration", [pid, str(record["_id"]), []], "scheduler_new")
    ]
    assert len(_claims(h)) == 1  # the link is consumed once a record exists
    assert _lock_keys(h) == []


def test_broker_error_after_the_insert_leaves_the_record_pending(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    from openwellness_api.event_handlers.ports import TaskPublishError

    pid = h.seed_participant()
    legacy = h.seed_legacy(pid)
    client, state, cookie = _prepared(h, pid, "c1")
    h.publisher.error = TaskPublishError("OperationalError")

    with caplog.at_level(logging.ERROR):
        resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_success(resp)
    (record,) = h.google_records()
    assert record["migrationStatus"] == "pending"
    superseded = h.db["fitbits"].find_one({"supersededBy": str(record["_id"])})
    assert superseded is not None and str(superseded["_id"]) == legacy
    assert "googleHealth/finishAuth publish failed: TaskPublishError" in caplog.text
    assert len(_claims(h)) == 1
    assert _lock_keys(h) == []


# --- the locks themselves -----------------------------------------------------------


def test_locks_are_released_only_by_their_owner(h: Harness) -> None:
    tokens = h.deps.tokens
    locks = tokens.acquire_locks("P1", "H1")
    assert locks is not None
    assert sorted(h.redis.keys("gh:lock:*")) == sorted(["gh:lock:pid:P1", _hu_key("H1")])
    assert 0 < h.redis.pttl("gh:lock:pid:P1") <= h.settings.lock_ttl_ms

    # Another request took the participant lock after ours expired.
    h.redis.set("gh:lock:pid:P1", "another-owner", px=60000)
    tokens.release_locks(locks)

    assert h.redis.get("gh:lock:pid:P1") == "another-owner"
    assert h.redis.get(_hu_key("H1")) is None


def test_a_refused_account_lock_releases_the_participant_lock(h: Harness) -> None:
    h.redis.set(_hu_key("H1"), "another-owner", px=60000)
    assert h.deps.tokens.acquire_locks("P1", "H1") is None
    assert h.redis.get("gh:lock:pid:P1") is None
    assert h.redis.get(_hu_key("H1")) == "another-owner"


def test_the_account_lock_key_never_carries_the_google_user_id(h: Harness) -> None:
    locks = h.deps.tokens.acquire_locks("P1", "HEALTH-USER-SENTINEL")
    assert locks is not None
    assert all("HEALTH-USER-SENTINEL" not in key for key in h.redis.keys("*"))
    h.deps.tokens.release_locks(locks)
    assert _lock_keys(h) == []


# --- the link claim itself ------------------------------------------------------------


def _now(h: Harness) -> int:
    return int(h.deps.tokens._clock())


def test_an_expired_link_cannot_be_claimed(h: Harness) -> None:
    tokens = h.deps.tokens
    assert tokens.claim_link("J1", _now(h)) is None
    assert tokens.claim_link("J1", _now(h) - 5) is None
    assert _claims(h) == []


def test_a_pending_claim_lives_only_the_lock_ttl_until_committed(h: Harness) -> None:
    tokens = h.deps.tokens
    exp = _now(h) + h.settings.link_ttl_seconds
    claim = tokens.claim_link("J1", exp)
    assert claim is not None
    assert 0 < h.redis.pttl(claim.key) <= h.settings.lock_ttl_ms
    assert tokens.claim_link("J1", exp) is None

    assert tokens.commit_link(claim, exp)
    assert h.redis.ttl(claim.key) > h.settings.lock_ttl_ms // 1000


def test_a_claim_is_released_and_committed_only_by_its_owner(h: Harness) -> None:
    tokens = h.deps.tokens
    exp = _now(h) + h.settings.link_ttl_seconds
    claim = tokens.claim_link("J1", exp)
    assert claim is not None

    # Ours expired and another request claimed the link.
    h.redis.set(claim.key, "another-owner", px=60000)
    assert tokens.release_link(claim)
    assert h.redis.get(claim.key) == "another-owner"
    assert not tokens.commit_link(claim, exp)
    assert 0 < h.redis.pttl(claim.key) <= 60000


def test_a_lost_claim_writes_no_record(h: Harness) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")

    def steal() -> None:
        # The pending claim expired mid-flow and another request took it.
        (key,) = _claims(h)
        h.redis.set(key, "another-owner", px=60000)

    _swap(h, store=HookedStore(h.deps.store, {"carried_migrated_at": steal}))
    resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_error(resp)
    assert h.google_records() == []
    assert h.publisher.calls == []
    (key,) = _claims(h)
    assert h.redis.get(key) == "another-owner"
    assert _lock_keys(h) == []


def test_a_failed_release_is_logged_and_the_pending_claim_expires(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    pid = h.seed_participant()
    client, state, cookie = _prepared(h, pid, "c1")
    h.google.fail_identity = True

    def broken_pipeline(*args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("injected")

    faulty = FaultyRedis(h.redis, set())
    faulty.pipeline = broken_pipeline  # type: ignore[method-assign]
    _swap(h, tokens=GoogleHealthTokens(h.settings, faulty))

    with caplog.at_level(logging.WARNING):
        resp = h.finish(client, code="c1", state=state, cookie=cookie)

    assert _is_error(resp)
    assert "googleHealth/finishAuth link release failed" in caplog.text
    (key,) = _claims(h)
    assert 0 < h.redis.pttl(key) <= h.settings.lock_ttl_ms
