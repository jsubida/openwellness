"""Durable, revocable refresh sessions in MongoDB.

``RefreshSessionStore`` owns *only* the persistence side of refresh-token
rotation: it stores one document per issued refresh token (keyed by the token's
sha256 hash — never the raw token), rotates a presented token into a fresh
child in the same family via a single-use compare-and-set, detects reuse of an
already-rotated/revoked token and revokes the entire token family, and offers
targeted/blanket revocation helpers.

It does **not** generate refresh tokens or hashes (the caller, via the token
service, mints the raw token and its sha256 hash and passes the *hash* in), mint
access JWTs, send email, or touch Redis/HTTP. Collaborators (a pymongo
``Collection`` handle and a tz-aware ``clock``) are injected; the store has no
module-level singletons and never reads ``os.environ``.

The rotation CAS — ``update_one({_id, rotatedAt: None, revoked: False},
{$set: {rotatedAt: now}})`` and asserting ``matched_count == 1`` — is the core
security property: it guarantees each refresh token can be consumed exactly
once. A presented token that is already rotated/revoked, or that loses the CAS
race to a concurrent rotation, is treated as reuse and revokes the whole family
*before* the error surfaces.

Correctness never relies on the TTL index alone: ``expiresAt`` is re-checked on
every consume (the TTL sweep is best-effort and lags in real Mongo and never
runs in ``mongomock``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from pymongo.errors import OperationFailure


def _as_utc(value: datetime) -> datetime:
    """Coerce a datetime read back from Mongo to tz-aware UTC.

    pymongo stores datetimes as UTC and (with the default codec options)
    returns them tz-*naive*. The injected clock is tz-aware, so comparing the
    two directly raises ``TypeError: can't compare offset-naive and
    offset-aware datetimes``. Treating a naive value as UTC restores a valid,
    correct comparison without depending on ``tz_aware=True`` codec options on
    the collection handle.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class RefreshInvalid(Exception):
    """Raised when a presented refresh token is unknown or expired.

    There is no family to defend in this case (the token was never a live,
    rotatable session), so nothing is revoked. The caller maps this to a 401.
    """


class RefreshReuse(Exception):
    """Raised when a presented refresh token has already been consumed/revoked.

    Covers an already-rotated or already-revoked token *and* a concurrent
    rotation that lost the CAS race. In every case the store has **already**
    revoked the entire token family (reason ``"reuse_detected"``) before this
    is raised. The caller maps this to a 401.
    """


@dataclass(frozen=True)
class RotationResult:
    """The identity carried forward from a successful rotation."""

    user_id: str
    participant_id: str | None
    family_id: str


class RefreshSessionStore:
    """Durable refresh-session persistence with rotation + reuse detection."""

    def __init__(
        self, *, collection: Any, clock: Callable[[], datetime]
    ) -> None:
        """Wire the store to its collaborators.

        Contract: the injected ``clock`` MUST return a timezone-aware UTC
        ``datetime`` (naive or non-UTC values break expiry comparison).
        """
        # ``collection`` is a pymongo Collection (mongomock in tests); typed
        # loosely as Any so this module carries no hard pymongo type dependency.
        self._collection = collection
        self._clock = clock

    # ----------------------------------------------------------------- #
    # ensure_indexes
    # ----------------------------------------------------------------- #
    def ensure_indexes(self) -> None:
        """Create the collection's indexes; idempotent (safe every startup).

        ``tokenHash`` is unique (one live session per token hash); ``familyId``
        and ``userId`` back the family-/user-scoped revocations; ``expiresAt``
        is a TTL index that lets Mongo sweep stale sessions (a best-effort
        backstop — consume still re-checks expiry explicitly).

        Each index is given an explicit, stable ``name`` so re-running with the
        same options is a true no-op on real Mongo. Note: changing an index's
        options later (e.g. flipping uniqueness, or a different
        ``expireAfterSeconds``) is NOT done in place — real Mongo raises
        ``IndexOptionsConflict`` for a same-name index with different options.
        Such a change requires a manual ``dropIndex`` first, then a restart.
        """
        try:
            self._collection.create_index(
                "tokenHash", unique=True, name="uq_token_hash"
            )
            self._collection.create_index("familyId", name="ix_family_id")
            self._collection.create_index("userId", name="ix_user_id")
            self._collection.create_index(
                "expiresAt", expireAfterSeconds=0, name="ttl_expires_at"
            )
        except OperationFailure as exc:
            raise RuntimeError(
                "Failed to ensure refresh-session indexes; an existing index "
                "may have conflicting options — drop it manually and restart"
            ) from exc

    # ----------------------------------------------------------------- #
    # create
    # ----------------------------------------------------------------- #
    def create(
        self,
        *,
        token_hash: str,
        user_id: str,
        participant_id: str | None,
        family_id: str,
        parent_id: str | None = None,
        expires_at: datetime,
        user_agent: str | None = None,
        ip: str | None = None,
        created_by: str,
    ) -> None:
        """Insert a fresh, live session document.

        Used for initial credential issuance (a brand-new family at
        login/registration) and internally as the rotated child insert. A
        ``family_id`` is not generated here — the caller (the service that owns
        token + family generation) supplies it.
        """
        now = self._clock()
        self._collection.insert_one(
            {
                "tokenHash": token_hash,
                "userId": user_id,
                "participantId": participant_id,
                "familyId": family_id,
                "parentId": parent_id,
                "issuedAt": now,
                "expiresAt": expires_at,
                "rotatedAt": None,
                "revoked": False,
                "revokedAt": None,
                "revokedReason": None,
                "userAgent": user_agent,
                "ip": ip,
                "createdBy": created_by,
            }
        )

    # ----------------------------------------------------------------- #
    # consume_for_rotation
    # ----------------------------------------------------------------- #
    def consume_for_rotation(
        self,
        *,
        presented_hash: str,
        new_token_hash: str,
        new_expires_at: datetime,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> RotationResult:
        """Single-use rotate ``presented_hash`` into a fresh child token.

        On success the presented session is marked consumed (``rotatedAt`` set)
        and a new live session is inserted in the same family. Raises
        :class:`RefreshInvalid` for an unknown/expired token (no family revoke)
        and :class:`RefreshReuse` for a reused/already-revoked token or a lost
        CAS race (the whole family is revoked first).
        """
        doc = self._collection.find_one({"tokenHash": presented_hash})
        if doc is None:
            # Unknown token: never a live session here, nothing to defend.
            raise RefreshInvalid("refresh token not found")

        # Already consumed or revoked → reuse: a live token was presented twice
        # (or after an explicit revoke). Burn the whole family, then signal.
        if doc["revoked"] or doc.get("rotatedAt") is not None:
            self.revoke_family(doc["familyId"], reason="reuse_detected")
            raise RefreshReuse("refresh token reuse detected")

        # Belt-and-suspenders expiry check beyond the TTL index (which lags in
        # real Mongo and never runs in mongomock). An expired token is invalid,
        # not reuse — it was never rotated, so there is no family to defend.
        if _as_utc(doc["expiresAt"]) < self._clock():
            raise RefreshInvalid("refresh token expired")

        # Conditional CAS consume: only one caller can flip rotatedAt from None,
        # guaranteeing single use. A zero match means a concurrent rotation/
        # revoke won the race → reuse → revoke the family.
        #
        # Single-use correctness relies on this conditional CAS *alone* — there
        # is no DB transaction wrapping the CAS and the child insert below (the
        # deployment is standalone Mongo 4.0, no multi-doc transactions).
        now = self._clock()
        res = self._collection.update_one(
            {"_id": doc["_id"], "rotatedAt": None, "revoked": False},
            {"$set": {"rotatedAt": now}},
        )
        if res.matched_count == 0:
            self.revoke_family(doc["familyId"], reason="reuse_detected")
            raise RefreshReuse("refresh token reuse detected (lost CAS race)")

        # CAS won: mint the child session in the same family, chained to the
        # parent so the rotation lineage is auditable. The CAS and this insert
        # are two non-atomic writes; if the insert fails we'd otherwise leave a
        # consumed parent with no child — a dead family that silently logs the
        # user out. So roll the parent back to usable and re-raise, letting the
        # caller retry with the SAME still-valid token (no lockout, no reuse).
        try:
            self.create(
                token_hash=new_token_hash,
                user_id=doc["userId"],
                participant_id=doc.get("participantId"),
                family_id=doc["familyId"],
                parent_id=str(doc["_id"]),
                expires_at=new_expires_at,
                user_agent=user_agent,
                ip=ip,
                created_by=doc["userId"],
            )
        except Exception:
            # Only flip rotatedAt back if it's still the value WE set — the
            # conditional filter on the exact `now` guards against clobbering a
            # concurrent change that legitimately re-consumed the parent.
            self._collection.update_one(
                {"_id": doc["_id"], "rotatedAt": now},
                {"$set": {"rotatedAt": None}},
            )
            raise
        return RotationResult(
            user_id=doc["userId"],
            participant_id=doc.get("participantId"),
            family_id=doc["familyId"],
        )

    # ----------------------------------------------------------------- #
    # revocation helpers
    # ----------------------------------------------------------------- #
    def _revocation_update(self, reason: str) -> dict:
        """The shared ``$set`` payload that marks a session revoked.

        Centralised so the three revoke_* helpers stay in lock-step (same
        fields, same clock read) if the revocation shape ever changes.
        """
        return {
            "$set": {
                "revoked": True,
                "revokedAt": self._clock(),
                "revokedReason": reason,
            }
        }

    def revoke_by_hash(self, token_hash: str, *, reason: str = "logout") -> None:
        """Revoke a single session by token hash; idempotent.

        Matching zero documents is fine (e.g. an already-expired/swept session
        on logout) — the API treats logout as an idempotent 200, so this never
        raises on a miss.
        """
        self._collection.update_one(
            {"tokenHash": token_hash}, self._revocation_update(reason)
        )

    def revoke_family(self, family_id: str, *, reason: str) -> None:
        """Revoke every session in a token family.

        Used by reuse detection (reason ``"reuse_detected"``) and available to
        the service for an explicit family kill.
        """
        self._collection.update_many(
            {"familyId": family_id}, self._revocation_update(reason)
        )

    def revoke_all_for_user(
        self, user_id: str, *, reason: str = "logout_all"
    ) -> None:
        """Revoke every session belonging to a user (global sign-out)."""
        self._collection.update_many(
            {"userId": user_id}, self._revocation_update(reason)
        )


__all__ = [
    "RefreshInvalid",
    "RefreshReuse",
    "RefreshSessionStore",
    "RotationResult",
]
