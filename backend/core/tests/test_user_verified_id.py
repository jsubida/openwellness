"""Tests for User.verified_id / User.registered_at round-tripping through MongoUser.

RED → these tests fail before the fields are added to User and MongoUser.
GREEN → they pass after both sides are updated symmetrically.
"""

from datetime import datetime

from bson import ObjectId

from openwellness_core.adapters.mongo.model import MongoUser
from openwellness_core.domain.models.user import User


# ---------------------------------------------------------------------------
# 1. Legacy doc round-trips: verifiedId / registeredAt survive to_domain
# ---------------------------------------------------------------------------


def test_legacy_doc_verified_id_survives_to_domain():
    """A Mongo document with verifiedId yields a User whose verified_id matches."""
    doc = {
        "_id": ObjectId(),
        "email": "a@b.com",
        "isActive": True,
        "username": "u",
        "verifiedId": "bcrypt$hash",
        "registeredAt": datetime(2024, 1, 15, 10, 30),
    }
    user = MongoUser.model_validate(doc).to_domain(User)
    assert user.verified_id == "bcrypt$hash"


def test_legacy_doc_registered_at_survives_to_domain():
    """A Mongo document with registeredAt yields a User whose registered_at is set."""
    registered = datetime(2024, 1, 15, 10, 30)
    doc = {
        "_id": ObjectId(),
        "email": "a@b.com",
        "isActive": True,
        "username": "u",
        "verifiedId": "bcrypt$hash",
        "registeredAt": registered,
    }
    user = MongoUser.model_validate(doc).to_domain(User)
    assert user.registered_at == registered


def test_legacy_doc_verified_id_as_hex_string_id():
    """ObjectId hex string in _id field is stringified; verifiedId still round-trips."""
    oid = ObjectId()
    doc = {
        "_id": str(oid),
        "email": "a@b.com",
        "isActive": True,
        "username": "u",
        "verifiedId": "bcrypt$hash2",
    }
    user = MongoUser.model_validate(doc).to_domain(User)
    assert user.verified_id == "bcrypt$hash2"


# ---------------------------------------------------------------------------
# 2. Domain → doc: verified_id serializes as verifiedId
# ---------------------------------------------------------------------------


def test_domain_to_doc_verified_id_uses_alias():
    """from_domain followed by model_dump(by_alias=True) emits camelCase verifiedId."""
    u = User(email="a@b.com", is_active=True, username="u", verified_id="x")
    doc = MongoUser.from_domain(u).model_dump(by_alias=True)
    assert "verifiedId" in doc
    assert doc["verifiedId"] == "x"


def test_domain_to_doc_registered_at_uses_alias():
    """from_domain followed by model_dump(by_alias=True) emits camelCase registeredAt."""
    reg = datetime(2025, 3, 20, 8, 0)
    u = User(email="a@b.com", is_active=True, username="u", registered_at=reg)
    doc = MongoUser.from_domain(u).model_dump(by_alias=True)
    assert "registeredAt" in doc
    assert doc["registeredAt"] == reg


# ---------------------------------------------------------------------------
# 3. Default is None / falsy: un-verified users have no verified_id
# ---------------------------------------------------------------------------


def test_user_default_verified_id_is_none():
    """A User constructed without verified_id has verified_id is None (falsy)."""
    u = User(email="a@b.com", is_active=True, username="u")
    assert u.verified_id is None


def test_user_default_registered_at_is_none():
    """A User constructed without registered_at has registered_at is None (falsy)."""
    u = User(email="a@b.com", is_active=True, username="u")
    assert u.registered_at is None
