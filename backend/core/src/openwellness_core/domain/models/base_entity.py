"""Universal base for all domain entities."""

from dataclasses import dataclass, field, fields
from typing import Self
from uuid import uuid4


@dataclass
class BaseEntity:
    """Universal base for all domain entities.

    Document `type` and collection routing are persistence concerns and live
    on the persistence-layer classes in `adapters/`, not here.

    `channels` and `_rev` are deliberately *not* among them. Sync Gateway's
    sync function reads access metadata from the document body itself, so
    `channels` decides who can read a document; a persistence layer that
    drops it on read writes it back empty and silently revokes access for
    every subscriber except the owner, with no error anywhere. `_rev` is what
    lets Sync Gateway enforce optimistic concurrency on updates. Both must
    therefore survive the document → entity → document round trip, which
    means being declared here so `valid_fields()` admits them.

    See `specs/004-write-correctness/`.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    # `None` (never carried channels) and `[]` (channels cleared) are
    # semantically distinct to Sync Gateway's `!= null` test and to the
    # write guard, so this must not default to an empty list.
    channels: list[str] | None = None
    # The leading underscore is deliberate, not a private-attribute
    # convention: it makes the generated `__init__` parameter `_rev`, which
    # is exactly what `CBBaseEntity.to_domain` constructs with after it
    # renames the wire field. Renaming it breaks the read path silently.
    _rev: str = ""

    @classmethod
    def valid_fields(cls) -> set[str]:
        """Return the set of declared field names for this entity."""
        return {f.name for f in fields(cls)}

    @classmethod
    def create(cls, data: dict) -> Self:
        """Construct an entity from a dict of field values."""
        return cls(**data)
