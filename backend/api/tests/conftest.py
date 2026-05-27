"""In-memory fakes + dependency overrides for the API tests.

The aim is to exercise the routers and the factories without hitting
Couchbase or Mongo. Each fake repo implements just enough of the public
methods that the API surface calls into.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

# Ensure config loads with safe defaults before the app imports.
os.environ.setdefault("COUCHBASE_URL", "couchbase://stub")
os.environ.setdefault("MONGO_URL", "mongodb://stub")

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openwellness_core.application.repositories import (
    ConditionRepository,
    ConversationRepository,
    GoalRepository,
    MessageRepository,
    ParticipantRepository,
    StudyRepository,
    UserRepository,
    WeightRepository,
)
from openwellness_core.domain.exceptions.domain_exception import (
    EntityNotFoundException,
)
from openwellness_core.domain.models.conversation import Conversation


class InMemoryBaseRepo:
    """Dict-backed implementation of ``BaseCrudRepository``."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.archived: dict[str, Any] = {}

    def create(self, entity: Any) -> Any:
        if not getattr(entity, "id", None):
            entity.id = str(uuid4())
        self.store[entity.id] = entity
        return entity

    def get_by_id(self, entity_id: str) -> Any | None:
        return self.store.get(entity_id)

    def get_by_query(self, query: Any) -> list[Any]:
        return list(self.store.values())

    def list_all(self) -> list[Any]:
        return list(self.store.values())

    def execute_query(self, query: Any) -> Any:
        return self.store.values()

    def save(self, entity: Any) -> Any:
        self.store[entity.id] = entity
        return entity

    def delete(self, entity_id: str) -> None:
        self.store.pop(entity_id, None)

    def archive(self, entity_id: str) -> None:
        entity = self.store.get(entity_id)
        if entity is None:
            raise EntityNotFoundException(f"{entity_id} not found")
        self.archived[entity_id] = entity

    def unarchive(self, entity_id: str) -> None:
        self.archived.pop(entity_id, None)


class InMemoryOwnerRepo(InMemoryBaseRepo):
    """Adds owner-aware queries on top of the base in-memory repo."""

    def get_for_owner(self, owner_id: str, arg: Any) -> Any | None:
        return next(
            (e for e in self.store.values() if getattr(e, "owner", None) == owner_id),
            None,
        )

    def get_for_owner_between(
        self, owner_id: str, start: Any, end: Any
    ) -> list[Any]:
        return [
            e
            for e in self.store.values()
            if getattr(e, "owner", None) == owner_id
        ]


class FakeUserRepo(InMemoryBaseRepo, UserRepository):
    pass


class FakeStudyRepo(InMemoryBaseRepo, StudyRepository):
    def get_by_name(self, name: str) -> Any | None:
        return next(
            (s for s in self.store.values() if getattr(s, "name", None) == name),
            None,
        )


class FakeWeightRepo(InMemoryOwnerRepo, WeightRepository):  # type: ignore[misc]
    pass


class FakeGoalRepo(InMemoryOwnerRepo, GoalRepository):  # type: ignore[misc]
    def get_all_for_owner(self, owner_id: str, arg: Any) -> list[Any]:
        return self.get_for_owner_between(owner_id, None, None)

    def get_all_for_owner_by_kind(
        self, owner_id: str, arg: Any, kind: Any | None = None
    ) -> list[Any]:
        items = self.get_for_owner_between(owner_id, None, None)
        if kind is None:
            return items
        return [e for e in items if int(getattr(e, "kind", -1)) == int(kind)]

    def get_all_for_owner_between(
        self, owner_id: str, start: Any, end: Any
    ) -> list[Any]:
        return self.get_for_owner_between(owner_id, start, end)

    def get_all_for_owner_by_kind_between(
        self, owner_id: str, start: Any, end: Any, kind: Any | None = None
    ) -> list[Any]:
        items = self.get_for_owner_between(owner_id, start, end)
        if kind is None:
            return items
        return [e for e in items if int(getattr(e, "kind", -1)) == int(kind)]

    def get_for_owner_by_kind(
        self, owner_id: str, arg: Any, kind: Any | None = None
    ) -> Any | None:
        items = self.get_all_for_owner_by_kind(owner_id, arg, kind)
        return items[0] if items else None

    def get_for_owner_by_kind_between(
        self, owner_id: str, start: Any, end: Any, kind: Any | None = None
    ) -> list[Any]:
        return self.get_all_for_owner_by_kind_between(owner_id, start, end, kind)


class FakeConditionRepo(InMemoryOwnerRepo, ConditionRepository):  # type: ignore[misc]
    pass


class FakeMessageRepo(InMemoryBaseRepo, MessageRepository):
    def get_for_owner_between(
        self,
        owner: str,
        start: Any,
        end: Any,
        subtype: int | None = None,
        condition: int | None = None,
    ) -> list[Any]:
        out = [
            e
            for e in self.store.values()
            if getattr(e, "owner", None) == owner
        ]
        if subtype is not None:
            out = [e for e in out if getattr(e, "subtype", None) == subtype]
        if condition is not None:
            out = [e for e in out if getattr(e, "condition", None) == condition]
        return out


class FakeConversationRepo(InMemoryBaseRepo, ConversationRepository):
    def get_for_filters(self, filters: list[Conversation.Filter]) -> list[Any]:
        out = list(self.store.values())
        for f in filters:
            if f.type is Conversation.Filter.Type.KIND:
                out = [c for c in out if c.kind == int(f.val)]
            # CHANNELS / WEEK aren't on the in-memory shape; ignored.
        return out


class FakeParticipantRepo(InMemoryBaseRepo, ParticipantRepository):
    def get_by_study_id(self, study_id: str) -> list[Any]:
        return [
            p
            for p in self.store.values()
            if str(getattr(p, "study_id", "")) == study_id
        ]

    def get_by_num_study_id(self, num: str, study_id: str) -> Any | None:
        return next(
            (
                p
                for p in self.store.values()
                if str(getattr(p, "study_id", "")) == study_id
                and getattr(p, "participant_number", "") == num
            ),
            None,
        )


@pytest.fixture
def fakes() -> dict[type, Any]:
    """Mapping from interface type to in-memory fake."""
    return {
        UserRepository: FakeUserRepo(),
        StudyRepository: FakeStudyRepo(),
        WeightRepository: FakeWeightRepo(),
        GoalRepository: FakeGoalRepo(),
        ConditionRepository: FakeConditionRepo(),
        MessageRepository: FakeMessageRepo(),
        ConversationRepository: FakeConversationRepo(),
        ParticipantRepository: FakeParticipantRepo(),
    }


# Interface → ``RepositoryContainer`` provider name. The test fakes are
# keyed by interface; routes resolve through the container, so we need a
# mapping from the test-side interface to the container's provider name.
_IFACE_TO_PROVIDER: dict[type, str] = {
    UserRepository: "user",
    StudyRepository: "study",
    WeightRepository: "weight",
    GoalRepository: "goal",
    ConditionRepository: "condition",
    MessageRepository: "message",
    ConversationRepository: "conversation",
    ParticipantRepository: "participant",
}

from openwellness_api.resources import RESOURCE_MODULES

_WIRED_MODULES = [mod.__name__ for mod in RESOURCE_MODULES]


@pytest.fixture
def app(fakes: dict[type, Any]):
    """App with fakes wired through an ``ApplicationContainer`` instance.

    We bypass the real lifespan (no Couchbase/Mongo connection), build a
    container, override each fake's provider with ``providers.Object(fake)``,
    and wire the resource modules so ``@inject`` markers see the overrides.
    """
    from openwellness_api.container import ApplicationContainer
    from openwellness_api.errors.handlers import register_exception_handlers
    from openwellness_api.v1 import build_v1_router

    instance = FastAPI(title="OpenWellness API (test)")
    register_exception_handlers(instance)
    instance.include_router(build_v1_router())

    container = ApplicationContainer()
    for iface, fake in fakes.items():
        provider_name = _IFACE_TO_PROVIDER[iface]
        getattr(container.repositories, provider_name).override(
            providers.Object(fake)
        )
    container.wire(modules=_WIRED_MODULES)
    instance.state.container = container

    yield instance

    container.unwire()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
