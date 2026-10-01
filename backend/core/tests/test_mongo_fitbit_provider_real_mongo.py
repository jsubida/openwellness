"""The ``fitbits`` provider filters against a real MongoDB (opserver 10.1-17).

mongomock can only show what mongomock does. These cases repeat the
visibility cases of ``test_mongo_fitbit_provider.py`` against a real server,
the ``mongo:4.0.6`` image frame's harness (10.1-03) uses.

Set ``GH_REAL_MONGO_URL`` (for example ``mongodb://127.0.0.1:27399``) to run
them. When the variable is unset the module skips; when it is set but the
server does not answer within 5 s, every test fails.
"""

import os
import uuid
from typing import Any, Iterator

import pytest
from pymongo import MongoClient

from openwellness_core.adapters.interfaces.collection_repository import (
    CollectionRepository,
)
from openwellness_core.adapters.mongo.repositories.mongo_fitbit_repository import (
    MongoFitbitRepository,
)
from openwellness_core.domain.models.fitbit import (
    D13_ALIASES,
    PROVIDER_GOOGLE_HEALTH,
    active_filter,
    google_active_filter,
    legacy_active_filter,
)

URL = os.environ.get("GH_REAL_MONGO_URL")

pytestmark = pytest.mark.skipif(not URL, reason="GH_REAL_MONGO_URL is not set")

P = "5f0c1e2d3a4b5c6d7e8f9a0b"


class RealCollectionRepository(CollectionRepository):
    """A ``CollectionRepository`` over one pymongo database."""

    def __init__(self, db: Any) -> None:
        self.db = db

    def __getattr__(self, name: str) -> Any:
        return self.db[name]

    def __getitem__(self, name: str) -> Any:
        return self.db[name]

    def list_collection_names(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.list_collection_names(*args, **kwargs)

    def create_collection(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_collection(name, *args, **kwargs)

    def drop_collection(self, name_or_collection: Any, *args: Any, **kwargs: Any) -> Any:
        return self.db.drop_collection(name_or_collection, *args, **kwargs)

    def command(self, command: Any, *args: Any, **kwargs: Any) -> Any:
        return self.db.command(command, *args, **kwargs)


@pytest.fixture
def db() -> Iterator[Any]:
    assert URL is not None
    client: MongoClient = MongoClient(URL, serverSelectionTimeoutMS=5000)
    # Fails (ServerSelectionTimeoutError) rather than skips when unreachable.
    client.admin.command("ping")
    name = f"gh_ow_{uuid.uuid4().hex[:12]}"
    try:
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def legacy_doc(**extra: Any) -> dict:
    doc = {
        "participantId": P,
        "accessToken": "legacy-access",
        "refreshToken": "legacy-refresh",
        "ownerId": "LEGACY1",
        "subscriptionId": "sub-1",
        "timeCreated": 1_700_000_000,
    }
    doc.update(extra)
    return doc


def google_doc(**extra: Any) -> dict:
    doc = {
        "participantId": P,
        "provider": PROVIDER_GOOGLE_HEALTH,
        "accessToken": "google-access",
        "refreshToken": "google-refresh",
        "expiresAt": 1_800_000_000,
        "scope": "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
        "healthUserId": "health-user-1",
        "legacyUserId": "LEGACY1",
        "timeCreated": 1_790_000_000,
        "migratedAt": 1_790_000_000,
        "migrationStatus": "pending",
        "reconsentRequiredAt": None,
        "lastSyncAt": None,
    }
    doc.update(extra)
    return doc


def seed_three_records(collection: Any) -> dict[str, Any]:
    """Active legacy, superseded legacy and Google, all for participant P."""
    google_id = collection.insert_one(google_doc()).inserted_id
    active_legacy_id = collection.insert_one(legacy_doc(ownerId="ACTIVE")).inserted_id
    superseded_id = collection.insert_one(
        legacy_doc(
            ownerId="SUPERSEDED",
            supersededAt=1_790_000_001,
            supersededBy=str(google_id),
        )
    ).inserted_id
    return {
        "google": google_id,
        "active_legacy": active_legacy_id,
        "superseded_legacy": superseded_id,
    }


def _ids(cursor: Any) -> set[Any]:
    return {doc["_id"] for doc in cursor}


def test_three_record_fixture_visibility_real_mongo(db: Any):
    ids = seed_three_records(db.fitbits)

    assert _ids(db.fitbits.find(legacy_active_filter())) == {ids["active_legacy"]}
    assert _ids(db.fitbits.find(google_active_filter())) == {ids["google"]}
    assert _ids(db.fitbits.find(active_filter())) == {
        ids["active_legacy"],
        ids["google"],
    }


def test_missing_provider_and_explicit_null_superseded_match_legacy_active_real_mongo(
    db: Any,
):
    no_provider = db.fitbits.insert_one(legacy_doc()).inserted_id
    explicit_null = db.fitbits.insert_one(
        legacy_doc(provider=None, supersededAt=None)
    ).inserted_id

    assert _ids(db.fitbits.find(legacy_active_filter())) == {no_provider, explicit_null}
    assert _ids(db.fitbits.find(active_filter())) == {no_provider, explicit_null}
    assert _ids(db.fitbits.find(google_active_filter())) == set()


def test_repository_resolves_migrated_participant_real_mongo(db: Any):
    ids = seed_three_records(db.fitbits)
    # Repair the fixture's I1 violation the way finishAuth leaves it:
    # only the Google record is active.
    db.fitbits.update_one(
        {"_id": ids["active_legacy"]},
        {"$set": {"supersededAt": 1_790_000_002, "supersededBy": str(ids["google"])}},
    )
    repo = MongoFitbitRepository(RealCollectionRepository(db))

    record = repo.get_by_participant_id(P)

    assert record is not None
    assert str(record.id) == str(ids["google"])
    assert record.provider == PROVIDER_GOOGLE_HEALTH


def test_saving_a_loaded_legacy_record_keeps_its_key_set_real_mongo(db: Any):
    legacy_id = db.fitbits.insert_one(legacy_doc()).inserted_id
    before = set(db.fitbits.find_one({"_id": legacy_id}))
    repo = MongoFitbitRepository(RealCollectionRepository(db))

    record = repo.get_by_participant_id(P)
    assert record is not None
    record.access_token = "refreshed-access"
    repo.save(record, actor="test")

    after = db.fitbits.find_one({"_id": legacy_id})
    assert set(after) == before
    assert after["accessToken"] == "refreshed-access"
    for alias in D13_ALIASES:
        assert alias not in after
