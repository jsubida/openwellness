"""Redis-backed OTP storage, verification, and rate-limit counters.

``RedisOtpStore`` owns *only* the Redis side of email-OTP auth: it persists a
hashed OTP record, verifies a candidate code atomically (single-use,
attempt-capped, constant-time), and enforces fixed-window send rate limits.

It does **not** generate the OTP code (the service passes a CSPRNG code in),
send email, or touch Mongo/HTTP. PII never lands in a key (emails are
normalised then SHA-256 hashed) and the plaintext code is never stored — only
an HMAC(pepper, salt+code) digest at rest.

Collaborators (a sync ``redis`` client and a tz-aware ``clock``) are injected;
the store has no module-level singletons and never reads ``os.environ``.

The injected redis client MUST be constructed with ``decode_responses=True``
(both ``redis.Redis`` in prod and ``fakeredis.FakeRedis`` in tests) so hash
fields and counters come back as ``str`` rather than ``bytes``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable

import redis.exceptions

from openwellness_core.application.exceptions import LimitExceededException

from openwellness_api.config import AuthSettings


class InvalidOtp(Exception):
    """Raised for a missing, expired, or wrong OTP code.

    The caller maps this to a single uniform 400 so a verify failure never
    leaks *why* it failed (missing vs expired vs wrong). Lockouts and
    rate-limits use :class:`LimitExceededException` (429) instead.
    """


# Bounded retry budget for the optimistic WATCH/MULTI verify loop. A retry only
# happens when the record key changed between WATCH and EXEC (concurrent
# verify/store), which is rare; the bound guards against pathological livelock.
_MAX_VERIFY_RETRIES = 5


class RedisOtpStore:
    """Hashed OTP records + atomic verify + fixed-window send rate limits."""

    def __init__(
        self,
        *,
        redis: Any,
        settings: AuthSettings,
        clock: Callable[[], datetime],
    ) -> None:
        self._redis = redis
        self._settings = settings
        self._clock = clock
        # Fail loud if the client was built without decode_responses=True: such
        # a client returns bytes, which silently breaks every verify (the hash
        # comparison never matches, every OTP becomes permanently unusable).
        probe_key = "otp:__decode_check__"
        self._redis.set(probe_key, "1", ex=1)
        if not isinstance(self._redis.get(probe_key), str):
            self._redis.delete(probe_key)
            raise ValueError(
                "RedisOtpStore requires a redis client constructed with "
                "decode_responses=True"
            )
        self._redis.delete(probe_key)

    # ----------------------------------------------------------------- #
    # Key helpers (PII never a plaintext key)
    # ----------------------------------------------------------------- #
    @staticmethod
    def _norm_email(email: str) -> str:
        return email.strip().lower()

    @classmethod
    def _email_hash(cls, email: str) -> str:
        return hashlib.sha256(cls._norm_email(email).encode()).hexdigest()

    def _record_key(self, purpose: str, email: str) -> str:
        return f"otp:{purpose}:{self._email_hash(email)}"

    def _send_key(self, purpose: str, email: str) -> str:
        return f"rl:send:{purpose}:{self._email_hash(email)}"

    def _resend_key(self, purpose: str, email: str) -> str:
        return f"rl:resend:{purpose}:{self._email_hash(email)}"

    def _ip_key(self, purpose: str, ip: str) -> str:
        return f"rl:ip:{purpose}:{ip}"

    def _lock_key(self, purpose: str, email: str) -> str:
        return f"lock:verify:{purpose}:{self._email_hash(email)}"

    # ----------------------------------------------------------------- #
    # Hashing (plaintext code NEVER stored)
    # ----------------------------------------------------------------- #
    def _hash_code(self, *, salt: str, code: str) -> str:
        return hmac.new(
            key=self._settings.code_pepper.encode(),
            msg=(salt + code).encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

    # ----------------------------------------------------------------- #
    # store_otp
    # ----------------------------------------------------------------- #
    def store_otp(
        self,
        *,
        purpose: str,
        email: str,
        code: str,
        user_id: str | None,
        participant_id: str | None,
    ) -> None:
        """Write a fresh hashed OTP record, overwriting any prior one.

        A new code resets ``attempts`` to 0. The record key TTL is the single
        source of expiry; the stored ``expiresAt`` is a belt-and-suspenders
        check applied at verify time.
        """
        now = self._clock()
        expires_at = now + timedelta(seconds=self._settings.otp_ttl_seconds)
        salt = secrets.token_hex(16)
        mapping = {
            "codeHash": self._hash_code(salt=salt, code=code),
            "salt": salt,
            "userId": user_id or "",
            "participantId": participant_id or "",
            "attempts": "0",
            "createdAt": now.isoformat(),
            "expiresAt": expires_at.isoformat(),
        }
        key = self._record_key(purpose, email)
        pipe = self._redis.pipeline()
        # DEL first so a re-store cannot inherit a stale `attempts` field from a
        # prior record (HSET only overwrites the keys it sets).
        pipe.delete(key)
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, self._settings.otp_ttl_seconds)
        pipe.execute()

    # ----------------------------------------------------------------- #
    # verify_otp
    # ----------------------------------------------------------------- #
    def verify_otp(
        self, *, purpose: str, email: str, code: str
    ) -> tuple[str | None, str | None]:
        """Atomically verify ``code``; return ``(user_id, participant_id)``.

        Single-use (record is DEL'd on success), attempt-capped (→ lockout),
        and constant-time. Raises :class:`InvalidOtp` for missing/expired/wrong
        and :class:`LimitExceededException` for lockout.
        """
        lock_key = self._lock_key(purpose, email)
        # Lockout check first — short-circuits before touching the record.
        lock_ttl = self._redis.ttl(lock_key)
        if lock_ttl is not None and lock_ttl > 0:
            raise LimitExceededException(
                "Too many attempts",
                retry_after_secs=int(lock_ttl),
            )

        record_key = self._record_key(purpose, email)
        max_attempts = self._settings.otp_max_attempts
        lockout_ttl = self._settings.otp_ttl_seconds

        for _ in range(_MAX_VERIFY_RETRIES):
            with self._redis.pipeline() as pipe:
                pipe.watch(record_key)
                record = pipe.hgetall(record_key)  # immediate-mode after watch
                if not record:
                    pipe.unwatch()
                    raise InvalidOtp("invalid or expired code")

                # Belt-and-suspenders explicit expiry vs the Redis TTL.
                expires_at = _parse_iso(record.get("expiresAt", ""))
                if expires_at is None or expires_at < self._clock():
                    pipe.multi()
                    pipe.delete(record_key)
                    try:
                        pipe.execute()
                    except redis.exceptions.WatchError:
                        continue
                    raise InvalidOtp("invalid or expired code")

                candidate = self._hash_code(
                    salt=record.get("salt", ""), code=code
                )
                stored = record.get("codeHash", "")

                if secrets.compare_digest(candidate, stored):
                    pipe.multi()
                    pipe.delete(record_key)
                    try:
                        pipe.execute()
                    except redis.exceptions.WatchError:
                        continue  # record changed concurrently → retry
                    return (
                        record.get("userId") or None,
                        record.get("participantId") or None,
                    )

                # Mismatch: persist the failed-attempt increment inside the same
                # WATCH/MULTI so the counter stays consistent with the value we
                # read (no torn read-modify-write across concurrent verifies).
                attempts = _to_int(record.get("attempts", "0"))
                new_attempts = attempts + 1
                if new_attempts >= max_attempts:
                    pipe.multi()
                    pipe.delete(record_key)
                    pipe.setex(lock_key, lockout_ttl, "1")
                    try:
                        pipe.execute()
                    except redis.exceptions.WatchError:
                        continue
                    raise LimitExceededException(
                        "Too many attempts",
                        retry_after_secs=lockout_ttl,
                    )

                pipe.multi()
                pipe.hincrby(record_key, "attempts", 1)
                try:
                    pipe.execute()
                except redis.exceptions.WatchError:
                    continue
                raise InvalidOtp("invalid or expired code")

        # Exhausted retries under sustained contention — treat as invalid
        # rather than leaking a partial success.
        raise InvalidOtp("invalid or expired code")

    # ----------------------------------------------------------------- #
    # check_send_limits
    # ----------------------------------------------------------------- #
    def check_send_limits(
        self, *, purpose: str, email: str, ip: str | None
    ) -> None:
        """Enforce resend cooldown + per-email + per-IP fixed-window limits.

        Records the send on success; raises :class:`LimitExceededException`
        (with ``retry_after_secs`` from the offending key's TTL) on the first
        limit hit. Resend cooldown is checked first so a burst is stopped early.
        """
        # 1. Resend cooldown — SET NX EX; absence of a set means still cooling.
        # A non-positive cooldown disables the check (Redis rejects EX 0).
        cooldown = self._settings.resend_cooldown_seconds
        if cooldown > 0:
            resend_key = self._resend_key(purpose, email)
            was_set = self._redis.set(resend_key, "1", nx=True, ex=cooldown)
            if not was_set:
                raise LimitExceededException(
                    "Resend too soon",
                    retry_after_secs=_ttl_or(self._redis, resend_key, cooldown),
                )

        # 2. Per-email fixed window. SET NX EX establishes the TTL atomically on
        # first use, *before* the INCR, so the counter can never outlive its
        # window (no INCR-without-EXPIRE gap if the process dies mid-call).
        send_key = self._send_key(purpose, email)
        send_window = self._settings.send_window_seconds
        self._redis.set(send_key, 0, nx=True, ex=send_window)
        count = int(self._redis.incr(send_key))
        if count > self._settings.send_max_per_window:
            raise LimitExceededException(
                "Too many requests",
                retry_after_secs=_ttl_or(self._redis, send_key, send_window),
            )

        # 3. Per-IP fixed window (only when an IP is supplied). Same atomic
        # SET-NX-EX-then-INCR pattern guarantees the TTL accompanies the count.
        if ip:
            ip_key = self._ip_key(purpose, ip)
            ip_window = self._settings.ip_window_seconds
            self._redis.set(ip_key, 0, nx=True, ex=ip_window)
            ip_count = int(self._redis.incr(ip_key))
            if ip_count > self._settings.ip_max_per_window:
                raise LimitExceededException(
                    "Too many requests",
                    retry_after_secs=_ttl_or(self._redis, ip_key, ip_window),
                )


# --------------------------------------------------------------------------- #
# Module-private helpers
# --------------------------------------------------------------------------- #
def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ttl_or(redis_client: Any, key: str, fallback: int) -> int:
    """Return the key's remaining TTL, or ``fallback`` if unset/expired.

    A fixed-window key always carries a TTL here, but a -1/-2/None TTL (no
    expiry / already gone due to a race) must still surface a sane positive
    ``Retry-After`` rather than a negative or zero value.
    """
    ttl = redis_client.ttl(key)
    if ttl is None or ttl <= 0:
        return fallback
    return int(ttl)
