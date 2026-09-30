"""The ``fitbits`` provider contract in OpenWellness core (opserver 10.1-17).

The contract is locked in opserver ``docs/google-health.md``, "Reference: the
contract". frame (10.1-03) and the scheduler (10.1-04) implement the same
filter documents and selection rule; these tests pin OpenWellness to them.

``mongomock`` is imported directly: a missing install fails the run rather
than skipping it.
"""

from typing import Any

import mongomock

from openwellness_core.adapters.interfaces.collection_repository import (
    CollectionRepository,
)
from openwellness_core.adapters.mongo.repositories.mongo_fitbit_repository import (
    MongoFitbitRepository,
)
from openwellness_core.domain.models.fitbit import (
    PROVIDER_GOOGLE_HEALTH,
    Fitbit,
)

P = "5f0c1e2d3a4b5c6d7e8f9a0b"

D13_SNAKE = (
    "provider",
    "expires_at",
    "scope",
    "health_user_id",
    "legacy_user_id",
    "superseded_at",
    "superseded_by",
    "migrated_at",
    "migration_status",
    "reconsent_required_at",
    "last_sync_at",
)


class RecordingCollection:
    """Wraps a mongomock collection and records every ``find`` query."""

    def __init__(self, inner: Any, queries: list[dict]) -> None:
        self._inner = inner
        self._queries = queries

    def find(self, query: dict, *args: Any, **kwargs: Any) -> Any:
        self._queries.append(query)
        return self._inner.find(query, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class FakeCollectionRepository(CollectionRepository):
    """A ``CollectionRepository`` backed by an in-memory mongomock database."""

    def __init__(self) -> None:
        self.db = mongomock.MongoClient().db
        self.queries: list[dict] = []

    def __getattr__(self, name: str) -> Any:
        return self[name]

    def __getitem__(self, name: str) -> Any:
        return RecordingCollection(self.db[name], self.queries)

    def list_collection_names(self, *args: Any, **kwargs: Any) -> Any:
        return self.db.list_collection_names(*args, **kwargs)

    def create_collection(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return self.db.create_collection(name, *args, **kwargs)

    def drop_collection(self, name_or_collection: Any, *args: Any, **kwargs: Any) -> Any:
        return self.db.drop_collection(name_or_collection, *args, **kwargs)

    def command(self, command: Any, *args: Any, **kwargs: Any) -> Any:
        return self.db.command(command, *args, **kwargs)


def legacy_doc(participant_id: str = P, **extra: Any) -> dict:
    """A legacy record as frame writes it: no provider, none of the D-13 fields."""
    doc = {
        "participantId": participant_id,
        "accessToken": "legacy-access",
        "refreshToken": "legacy-refresh",
        "ownerId": "LEGACY1",
        "subscriptionId": "sub-1",
        "timeCreated": 1_700_000_000,
    }
    doc.update(extra)
    return doc


def google_doc(participant_id: str = P, **extra: Any) -> dict:
    """A Google Health record as ``ow_api`` finishAuth writes it (D-13)."""
    doc = {
        "participantId": participant_id,
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


def make_repo() -> tuple[FakeCollectionRepository, MongoFitbitRepository]:
    fake = FakeCollectionRepository()
    return fake, MongoFitbitRepository(fake)


# --- Task 1 tracer: a migrated participant resolves to the Google record ---


def test_migrated_participant_resolves_to_google_record():
    fake, repo = make_repo()
    google_id = fake.db.fitbits.insert_one(google_doc()).inserted_id
    fake.db.fitbits.insert_one(
        legacy_doc(supersededAt=1_790_000_001, supersededBy=str(google_id))
    )

    record = repo.get_by_participant_id(P)

    assert record is not None
    assert str(record.id) == str(google_id)
    assert record.provider == "googleHealth"
    assert record.health_user_id == "health-user-1"
    assert record.expires_at == 1_800_000_000
    assert record.scope is not None


def test_get_by_participant_id_sends_the_active_query():
    fake, repo = make_repo()

    repo.get_by_participant_id(P)

    assert fake.queries == [{"participantId": P, "supersededAt": None}]


def test_legacy_document_loads_with_all_d13_attributes_none():
    fake, repo = make_repo()
    legacy_id = fake.db.fitbits.insert_one(legacy_doc()).inserted_id

    record = repo.get_by_participant_id(P)

    assert isinstance(record, Fitbit)
    assert str(record.id) == str(legacy_id)
    assert record.owner_id == "LEGACY1"
    for name in D13_SNAKE:
        assert getattr(record, name) is None, name
