"""Smoke tests: round-trip representative entities through their persistence DTOs.

Acceptance check for the `common/ → core/` port: each representative entity
survives `from_domain → model_dump → model_validate → to_domain` with the
core domain fields intact.
"""

from bson import ObjectId

from openwellness_core.adapters.couchbase.model import (
    CBBaseOwnerEntity,
    CBGoal,
    CBParticipantGroup,
    CBWeight,
)
from openwellness_core.adapters.mongo.model import (
    MongoStudy,
    MongoUser,
)
from openwellness_core.domain.models.base_entity import BaseEntity
from openwellness_core.domain.models.base_owner_entity import BaseOwnerEntity
from openwellness_core.domain.models.goal import Goal
from openwellness_core.domain.models.participant_group import ParticipantGroup
from openwellness_core.domain.models.study import Study
from openwellness_core.domain.models.user import User
from openwellness_core.domain.models.weight import Weight


def _cb_roundtrip(persistence_cls, domain_cls, domain_instance):
    """Helper: domain → CB persistence → wire dict → CB persistence → domain."""
    persistence = persistence_cls.from_domain(domain_instance)
    wire = persistence.model_dump(by_alias=True)
    rebuilt = persistence_cls.model_validate(wire)
    return rebuilt.to_domain(domain_cls)


def _mongo_roundtrip(persistence_cls, domain_cls, domain_instance):
    """Helper: domain → Mongo persistence → wire dict → Mongo persistence → domain."""
    persistence = persistence_cls.from_domain(domain_instance)
    wire = persistence.model_dump(by_alias=True)
    # Simulate Mongo assigning an ObjectId on insert.
    if not isinstance(wire.get("_id"), ObjectId) or wire["_id"] is None:
        wire["_id"] = ObjectId()
    rebuilt = persistence_cls.model_validate(wire)
    return rebuilt.to_domain(domain_cls)


def test_base_entity_defaults_have_id():
    e = BaseEntity()
    assert e.id, "BaseEntity should default `id` to a non-empty value"


def test_base_owner_entity_audit_defaults():
    e = BaseOwnerEntity(owner="p1", study_id="s1")
    assert e.owner == "p1"
    assert e.study_id == "s1"
    # __post_init__ defaults updated_by to owner when not given.
    assert e.updated_by == "p1"
    assert e.created_at > 0
    assert e.updated_at > 0


def test_cb_weight_roundtrip():
    w = Weight(owner="p1", study_id="s1", weight=180.5)
    w_back = _cb_roundtrip(CBWeight, Weight, w)
    assert w_back.owner == "p1"
    assert w_back.study_id == "s1"
    assert w_back.weight == 180.5
    assert w_back.id == w.id


def test_cb_goal_roundtrip():
    g = Goal(owner="p1", study_id="s1", start_date=1700000000.0)
    g_back = _cb_roundtrip(CBGoal, Goal, g)
    assert g_back.owner == "p1"
    assert g_back.study_id == "s1"
    assert g_back.start_date == 1700000000.0


def test_cb_participant_group_channels_derivation():
    """ParticipantGroup channels are derived in the persistence mapper."""
    pg = ParticipantGroup(
        owner="p1", study_id="s1", participant_ids=["a", "b"], pid_to_mid={}
    )
    persistence = CBParticipantGroup.from_domain(pg)
    assert persistence.channels == [f"participantGroup:{pg.id}"]


def test_cb_archived_writes_archived_type():
    """`from_domain(archived=True)` flips the wire-format `type` to `<Type>Archived`."""
    w = Weight(owner="p1", study_id="s1", weight=180.5)
    archived = CBWeight.from_domain(w, archived=True)
    doc = archived.model_dump(by_alias=True)
    assert doc["type"] == "WeightArchived"


def test_cb_persistence_owns_routing_fields():
    """`type`, `rev`/`_rev`, and `channels` are on the persistence layer only."""
    w = Weight(owner="p1", study_id="s1", weight=180.5)
    # Domain does NOT have these
    assert not hasattr(w, "type")
    assert not hasattr(w, "_rev")
    assert not hasattr(w, "channels")
    # Persistence DOES have them
    persistence = CBWeight.from_domain(w)
    assert CBWeight.type == "Weight"
    assert persistence.rev == ""
    assert persistence.channels is None


def test_mongo_user_roundtrip():
    u = User(email="a@b.com", is_active=True, username="alice")
    u_back = _mongo_roundtrip(MongoUser, User, u)
    assert u_back.email == "a@b.com"
    assert u_back.username == "alice"
    assert u_back.is_active is True


def test_mongo_study_roundtrip():
    from datetime import datetime

    s = Study(app_id="app1", name="S1", time_created=datetime(2024, 1, 1))
    s_back = _mongo_roundtrip(MongoStudy, Study, s)
    assert s_back.app_id == "app1"
    assert s_back.name == "S1"


def test_mongo_persistence_owns_collection_routing():
    """Collection name lives on the persistence class, not the domain."""
    assert MongoUser.collection == "users"
    assert MongoStudy.collection == "studies"
    # Domain class has no `collection()` method
    assert not hasattr(User, "collection")
    assert not hasattr(Study, "collection")


def test_archive_is_on_base_repository_interface():
    """`archive` is a base-repository concern, not a domain concern."""
    from openwellness_core.application.repositories.base_crud_repository import (
        BaseCrudRepository,
    )

    assert "archive" in BaseCrudRepository.__abstractmethods__
    # Domain bases have no `archive()` method
    assert not hasattr(BaseEntity, "archive")
    assert not hasattr(BaseOwnerEntity, "archive")


def test_cbbase_owner_entity_has_audit_fields():
    """CBBaseOwnerEntity exposes the owner/study/audit field set."""
    fields = set(CBBaseOwnerEntity.model_fields.keys())
    expected = {
        "id",
        "rev",
        "channels",
        "owner",
        "study_id",
        "created_at",
        "updated_at",
        "updated_by",
        "created_at_tz_offset",
        "updated_at_tz_offset",
    }
    assert expected.issubset(fields), f"Missing fields: {expected - fields}"
