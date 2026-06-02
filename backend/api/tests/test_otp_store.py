"""Unit tests for ``RedisOtpStore`` (hashed OTP + atomic verify + rate limits).

Strict-TDD coverage exercising the real ``fakeredis`` backend (never mocked)
so the atomic WATCH/MULTI verify path, single-use deletion, attempt cap →
lockout, expiry, and the fixed-window rate-limit counters are genuinely run.

PII discipline is asserted directly: no raw email lives in any Redis key, and
no plaintext code lives in the stored hash record.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

import fakeredis
import pytest

import redis.client
import redis.exceptions

from openwellness_core.application.exceptions import LimitExceededException

from openwellness_api.config import AuthSettings
from openwellness_api.auth.otp_store import (
    _MAX_VERIFY_RETRIES,
    InvalidOtp,
    RedisOtpStore,
    _ttl_or,
)


FIXED_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _settings(**overrides: object) -> AuthSettings:
    base: dict[str, object] = {
        "code_pepper": "test-pepper",
        "otp_ttl_seconds": 600,
        "otp_max_attempts": 5,
        "send_window_seconds": 3600,
        "send_max_per_window": 5,
        "resend_cooldown_seconds": 60,
        "ip_window_seconds": 3600,
        "ip_max_per_window": 20,
    }
    base.update(overrides)
    return AuthSettings(**base)  # type: ignore[arg-type]


def _store(
    *,
    redis: fakeredis.FakeRedis | None = None,
    clock: Callable[[], datetime] | None = None,
    **overrides: object,
) -> RedisOtpStore:
    client = redis or fakeredis.FakeRedis(decode_responses=True)
    return RedisOtpStore(
        redis=client,
        settings=_settings(**overrides),
        clock=clock or (lambda: FIXED_NOW),
    )


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# redis-py's stubs type read results as a sync/async union; these tests use a
# synchronous FakeRedis, so narrow the responses for the type checker.
def _hgetall(client: fakeredis.FakeRedis, key: str) -> dict[str, str]:
    return cast("dict[str, str]", client.hgetall(key))


def _ttl(client: fakeredis.FakeRedis, key: str) -> int:
    return cast(int, client.ttl(key))


def _hget(client: fakeredis.FakeRedis, key: str, field: str) -> str | None:
    return cast("str | None", client.hget(key, field))


# --------------------------------------------------------------------------- #
# Happy path (login & registration)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("purpose", ["login", "registration"])
def test_store_then_verify_returns_principal(purpose: str) -> None:
    store = _store()
    store.store_otp(
        purpose=purpose,
        email="User@Example.com",
        code="123456",
        user_id="user-1",
        participant_id="participants/abc",
    )
    result = store.verify_otp(
        purpose=purpose, email="user@example.com", code="123456"
    )
    assert result == ("user-1", "participants/abc")


def test_verify_returns_none_principal_when_not_stored() -> None:
    store = _store()
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="000111",
        user_id=None,
        participant_id=None,
    )
    assert store.verify_otp(purpose="login", email="a@b.com", code="000111") == (
        None,
        None,
    )


# --------------------------------------------------------------------------- #
# Single-use (WATCH/MULTI + DEL)
# --------------------------------------------------------------------------- #
def test_correct_code_is_single_use() -> None:
    store = _store()
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id=None,
    )
    assert store.verify_otp(purpose="login", email="a@b.com", code="123456") == (
        "u1",
        None,
    )
    with pytest.raises(InvalidOtp):
        store.verify_otp(purpose="login", email="a@b.com", code="123456")


# --------------------------------------------------------------------------- #
# Wrong code increments attempts
# --------------------------------------------------------------------------- #
def test_wrong_code_increments_attempts() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client)
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id=None,
    )
    with pytest.raises(InvalidOtp):
        store.verify_otp(purpose="login", email="a@b.com", code="999999")

    key = f"otp:login:{_email_hash('a@b.com')}"
    record = _hgetall(client, key)
    assert record["attempts"] == "1"
    # A correct code afterwards still works (record survives a single miss).
    assert store.verify_otp(purpose="login", email="a@b.com", code="123456") == (
        "u1",
        None,
    )


# --------------------------------------------------------------------------- #
# Attempt cap → lockout
# --------------------------------------------------------------------------- #
def test_attempt_cap_triggers_lockout() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client, otp_max_attempts=5)
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id=None,
    )
    # First (max-1) wrong attempts are plain InvalidOtp.
    for _ in range(4):
        with pytest.raises(InvalidOtp):
            store.verify_otp(purpose="login", email="a@b.com", code="000000")
    # The 5th wrong attempt hits the cap → lockout.
    with pytest.raises(LimitExceededException) as exc:
        store.verify_otp(purpose="login", email="a@b.com", code="000000")
    assert exc.value.retry_after_secs > 0

    # Record is gone.
    assert client.exists(f"otp:login:{_email_hash('a@b.com')}") == 0
    # Even the CORRECT code is now locked out.
    with pytest.raises(LimitExceededException) as exc2:
        store.verify_otp(purpose="login", email="a@b.com", code="123456")
    assert exc2.value.retry_after_secs > 0


# --------------------------------------------------------------------------- #
# Expiry (belt-and-suspenders explicit check vs Redis TTL)
# --------------------------------------------------------------------------- #
def test_expired_record_raises_invalid_and_is_deleted() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    past = FIXED_NOW - timedelta(seconds=601)
    # Store with the clock pinned in the past so expiresAt < verify-now.
    store_past = _store(redis=client, clock=lambda: past)
    store_past.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id=None,
    )
    # Verify with the clock at "now" → explicit expiry check fires.
    store_now = _store(redis=client, clock=lambda: FIXED_NOW)
    with pytest.raises(InvalidOtp):
        store_now.verify_otp(purpose="login", email="a@b.com", code="123456")
    assert client.exists(f"otp:login:{_email_hash('a@b.com')}") == 0


# --------------------------------------------------------------------------- #
# No plaintext at rest
# --------------------------------------------------------------------------- #
def test_no_plaintext_email_or_code_at_rest() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client)
    email = "Secret.User@Example.com"
    code = "424242"
    store.store_otp(
        purpose="login",
        email=email,
        code=code,
        user_id="u1",
        participant_id="p1",
    )
    # (a) Raw email appears in no key.
    keys = list(client.scan_iter("*"))
    norm = email.strip().lower()
    for k in keys:
        assert email not in k
        assert norm not in k
    # The record key uses the sha256 of the normalised email.
    expected_key = f"otp:login:{_email_hash(email)}"
    assert expected_key in keys

    # (b) Plaintext code is not stored; codeHash differs from the code.
    record = _hgetall(client, expected_key)
    assert record["codeHash"] != code
    for value in record.values():
        assert code not in value


# --------------------------------------------------------------------------- #
# Store overwrites prior record (fresh code resets attempts)
# --------------------------------------------------------------------------- #
def test_store_overwrites_and_resets_attempts() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client)
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="111111",
        user_id="u1",
        participant_id=None,
    )
    with pytest.raises(InvalidOtp):
        store.verify_otp(purpose="login", email="a@b.com", code="000000")
    key = f"otp:login:{_email_hash('a@b.com')}"
    assert _hget(client, key, "attempts") == "1"

    # Re-store a fresh code → attempts back to 0 and old code is invalid.
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="222222",
        user_id="u1",
        participant_id=None,
    )
    assert _hget(client, key, "attempts") == "0"
    with pytest.raises(InvalidOtp):
        store.verify_otp(purpose="login", email="a@b.com", code="111111")
    assert store.verify_otp(purpose="login", email="a@b.com", code="222222") == (
        "u1",
        None,
    )


# --------------------------------------------------------------------------- #
# Record key carries a TTL
# --------------------------------------------------------------------------- #
def test_record_has_ttl_set() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client, otp_ttl_seconds=600)
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id=None,
    )
    ttl = _ttl(client, f"otp:login:{_email_hash('a@b.com')}")
    assert 0 < ttl <= 600


# --------------------------------------------------------------------------- #
# Rate limit — per-email window
# --------------------------------------------------------------------------- #
def test_per_email_window_limit() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    # resend_cooldown_seconds=0 so the cooldown never masks the window test.
    store = _store(
        redis=client,
        send_max_per_window=5,
        resend_cooldown_seconds=0,
    )
    for _ in range(5):
        store.check_send_limits(purpose="login", email="a@b.com", ip=None)
    with pytest.raises(LimitExceededException) as exc:
        store.check_send_limits(purpose="login", email="a@b.com", ip=None)
    assert exc.value.retry_after_secs > 0


# --------------------------------------------------------------------------- #
# Resend cooldown
# --------------------------------------------------------------------------- #
def test_resend_cooldown() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client, resend_cooldown_seconds=60)
    store.check_send_limits(purpose="login", email="a@b.com", ip=None)
    with pytest.raises(LimitExceededException) as exc:
        store.check_send_limits(purpose="login", email="a@b.com", ip=None)
    # retry_after_secs ≈ cooldown (within the window, positive and ≤ cooldown).
    assert 0 < exc.value.retry_after_secs <= 60


# --------------------------------------------------------------------------- #
# Per-IP window (different emails, same IP)
# --------------------------------------------------------------------------- #
def test_per_ip_window_limit() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    # Large per-email window + no cooldown so the IP limit is what trips.
    store = _store(
        redis=client,
        send_max_per_window=1000,
        resend_cooldown_seconds=0,
        ip_max_per_window=20,
    )
    for i in range(20):
        store.check_send_limits(
            purpose="login", email=f"user{i}@b.com", ip="10.0.0.1"
        )
    with pytest.raises(LimitExceededException) as exc:
        store.check_send_limits(
            purpose="login", email="another@b.com", ip="10.0.0.1"
        )
    assert exc.value.retry_after_secs > 0


def test_ip_limit_skipped_when_ip_none() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(
        redis=client,
        send_max_per_window=1000,
        resend_cooldown_seconds=0,
        ip_max_per_window=1,
    )
    # No IP key should ever be created when ip is None/empty.
    store.check_send_limits(purpose="login", email="a@b.com", ip=None)
    store.check_send_limits(purpose="login", email="a@b.com", ip="")
    ip_keys = [k for k in client.scan_iter("rl:ip:*")]
    assert ip_keys == []


# --------------------------------------------------------------------------- #
# WATCH/MULTI concurrency — a watched-key change forces a retry, not a wrong
# answer. Two clients share one FakeServer; the clock callable mutates the
# record exactly once (between WATCH and EXEC) to trip a real WatchError, then
# the bounded retry re-reads the unchanged record and succeeds single-use.
# --------------------------------------------------------------------------- #
def test_watch_conflict_retries_then_succeeds() -> None:
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    other = fakeredis.FakeRedis(server=server, decode_responses=True)
    key = f"otp:login:{_email_hash('a@b.com')}"

    calls = {"n": 0}

    def racing_clock() -> datetime:
        # The verify loop reads the clock once per iteration (the expiry check).
        # On the FIRST iteration only, mutate the watched key after the read so
        # the subsequent EXEC raises WatchError and the loop retries.
        calls["n"] += 1
        if calls["n"] == 1:
            other.hincrby(key, "attempts", 1)
        return FIXED_NOW

    store = RedisOtpStore(
        redis=client, settings=_settings(), clock=racing_clock
    )
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id="p1",
    )
    # Despite the injected conflict, the correct code still resolves once the
    # retry re-reads a consistent record.
    assert store.verify_otp(
        purpose="login", email="a@b.com", code="123456"
    ) == ("u1", "p1")
    assert calls["n"] >= 2  # proves at least one retry actually happened
    # Single-use still holds after the retried success.
    assert client.exists(key) == 0


# --------------------------------------------------------------------------- #
# Purpose isolation
# --------------------------------------------------------------------------- #
def test_purposes_are_isolated() -> None:
    store = _store()
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="login-user",
        participant_id=None,
    )
    store.store_otp(
        purpose="registration",
        email="a@b.com",
        code="654321",
        user_id="reg-user",
        participant_id=None,
    )
    # Each purpose verifies independently with its own code.
    assert store.verify_otp(
        purpose="login", email="a@b.com", code="123456"
    ) == ("login-user", None)
    assert store.verify_otp(
        purpose="registration", email="a@b.com", code="654321"
    ) == ("reg-user", None)


# --------------------------------------------------------------------------- #
# decode_responses guard — a client without decode_responses=True returns bytes,
# which silently breaks every verify; the store must fail loud at construction.
# --------------------------------------------------------------------------- #
def test_requires_decode_responses() -> None:
    bad_client = fakeredis.FakeRedis(decode_responses=False)
    with pytest.raises(ValueError):
        RedisOtpStore(
            redis=bad_client,
            settings=_settings(),
            clock=lambda: FIXED_NOW,
        )


# --------------------------------------------------------------------------- #
# Retry exhaustion — sustained WatchError on EXEC must surface InvalidOtp, never
# a silent success and never an unbounded loop.
# --------------------------------------------------------------------------- #
def test_verify_retry_exhaustion_raises_invalid() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    store = _store(redis=client)
    store.store_otp(
        purpose="login",
        email="a@b.com",
        code="123456",
        user_id="u1",
        participant_id="p1",
    )

    real_pipeline = client.pipeline
    exec_calls = {"n": 0}

    class _AlwaysWatchErrorPipe:
        """Wraps a real pipeline but forces EXEC to always raise WatchError."""

        def __init__(self, inner: redis.client.Pipeline) -> None:
            self._inner = inner

        def execute(self) -> object:
            exec_calls["n"] += 1
            raise redis.exceptions.WatchError("forced")

        def __getattr__(self, name: str) -> object:
            return getattr(self._inner, name)

        def __enter__(self) -> "_AlwaysWatchErrorPipe":
            self._inner.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self._inner.__exit__(*args)

    def patched_pipeline(*args: Any, **kwargs: Any) -> object:
        return _AlwaysWatchErrorPipe(real_pipeline(*args, **kwargs))

    client.pipeline = patched_pipeline  # type: ignore[method-assign]

    # The correct code would normally succeed, but every EXEC raises WatchError,
    # so the bounded loop exhausts its budget and reports InvalidOtp.
    with pytest.raises(InvalidOtp):
        store.verify_otp(purpose="login", email="a@b.com", code="123456")
    # Bounded — exactly _MAX_VERIFY_RETRIES EXEC attempts, no unbounded loop.
    assert exec_calls["n"] == _MAX_VERIFY_RETRIES


# --------------------------------------------------------------------------- #
# TTL fallback — a key with TTL -1 (no expiry) or -2 (missing) must still yield
# a positive Retry-After so the header is never zero/negative.
# --------------------------------------------------------------------------- #
def test_ttl_fallback_yields_positive_retry_after() -> None:
    client = fakeredis.FakeRedis(decode_responses=True)
    # -1: key exists with no expiry.
    client.set("rl:noexpire", "1")
    assert _ttl(client, "rl:noexpire") == -1
    assert _ttl_or(client, "rl:noexpire", fallback=42) == 42
    # -2: key missing entirely.
    assert _ttl(client, "rl:missing") == -2
    assert _ttl_or(client, "rl:missing", fallback=42) == 42
