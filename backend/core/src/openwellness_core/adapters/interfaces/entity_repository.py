"""Abstract Couchbase entity repository."""

from abc import ABC, abstractmethod
from typing import Optional


class EntityRepository(ABC):
    """Abstract base class for Couchbase port operations."""

    @property
    @abstractmethod
    def bucket(self) -> str:
        """The bucket name to use for the Couchbase connection."""

    @abstractmethod
    def get_by_id(self, doc_id: str) -> Optional[dict]:
        """Fetch an object of type dict by its ID."""

    @abstractmethod
    def get_by_query(
        self, query: str, params: dict | None = None
    ) -> list[dict]:
        """Fetch objects of type dict via N1QL query.

        All user-supplied values must be passed via ``params`` (named
        parameters: ``$name`` in ``query``). Only the bucket name and
        allowlisted column identifiers may be interpolated into ``query``.
        """

    @abstractmethod
    def create(self, obj: dict, *, actor: str) -> dict:
        """Create a new object.

        ``actor`` names the identity recorded on the stored document as the
        one that performed the write. It is required and keyword-only: the
        caller knows who acted, the driver does not. Implementations must
        record the supplied value and must **not** substitute a default,
        a service name, or a value read back off ``obj``.
        """

    @abstractmethod
    def update(self, doc_id: str, obj: dict, *, actor: str) -> dict:
        """Update an object by its ID.

        ``actor`` names the identity recorded on the stored document as the
        one that performed the write. It is required and keyword-only: the
        caller knows who acted, the driver does not. Implementations must
        record the supplied value and must **not** substitute a default,
        a service name, or a value read back off ``obj``.
        """

    @abstractmethod
    def save(self, obj: dict, *, actor: str) -> dict:
        """Save an object.

        ``actor`` names the identity recorded on the stored document as the
        one that performed the write. It is required and keyword-only: the
        caller knows who acted, the driver does not. Implementations must
        record the supplied value and must **not** substitute a default,
        a service name, or a value read back off ``obj``.
        """

    @abstractmethod
    def delete(self, doc_id: str) -> dict | None:
        """Delete an object by its ID."""
