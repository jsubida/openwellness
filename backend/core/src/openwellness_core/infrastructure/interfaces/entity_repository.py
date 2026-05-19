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
    def get_by_query(self, query: str) -> list[dict]:
        """Fetch objects of type dict via N1QL query."""

    @abstractmethod
    def create(self, obj: dict) -> dict:
        """Create a new object."""

    @abstractmethod
    def update(self, doc_id: str, obj: dict) -> dict:
        """Update an object by its ID."""

    @abstractmethod
    def save(self, obj: dict) -> dict:
        """Save an object."""

    @abstractmethod
    def delete(self, doc_id: str) -> dict | None:
        """Delete an object by its ID."""
