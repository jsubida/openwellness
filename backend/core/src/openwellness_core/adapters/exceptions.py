"""Adapter-layer exceptions."""

from ..application.exceptions import LimitExceededException

__all__ = [
    "AdapterException",
    "ChannelsInvariantError",
    "LimitExceededException",
    "RevisionConflictError",
]


class AdapterException(Exception):
    """Base class for adapter-layer exceptions."""


class ChannelsInvariantError(AdapterException):
    """Raised when a write would destroy an existing document's access.

    Sync Gateway reads access metadata from the document body, so a write
    that clears a previously non-empty ``channels`` array revokes the
    document for every subscriber except its owner — silently, with no HTTP
    error anywhere and no signal on the participants' devices.

    Rejection semantics: when the prior revision carried a non-empty array,
    both a null value and an empty list are refused, and refused
    identically. The production sync function tests
    ``if (doc.channels != null)``; an empty array passes that test but
    contributes nothing, so the combined channel set collapses to
    ``[doc.owner]`` either way. Rejecting only the null spelling would leave
    the same hole open under the other one.

    The stored document is left untouched: the guard raises before the
    driver is called, so a rejected write cannot have partially applied.

    Not retryable. This indicates a caller bug — the caller must supply the
    correct channels (usually by loading the entity through its repository
    rather than constructing it by hand).

    See ``specs/004-write-correctness/design.md``.
    """

    def __init__(
        self,
        *args: object,
        doc_id: str,
        doc_type: str,
        prior_channels: list[str] | None,
        outgoing_channels: list[str] | None,
    ) -> None:
        self.doc_id = doc_id
        self.doc_type = doc_type
        self.prior_channels = prior_channels
        self.outgoing_channels = outgoing_channels
        super().__init__(*args)

    def __str__(self) -> str:
        return (
            f"Channels invariant violated for {self.doc_id} "
            f"(type={self.doc_type}); prior channels={self.prior_channels}, "
            f"attempted channels={self.outgoing_channels}"
        )


class RevisionConflictError(AdapterException):
    """Raised when Sync Gateway rejects a write for a stale revision.

    Sync Gateway enforces optimistic concurrency on updates: a write
    carrying a revision that is no longer current is answered with a
    conflict rather than applied.

    The adapter performs **no** automatic retry and **no** merge. Re-sending
    the same body under the current revision would overwrite whatever change
    produced the conflict, which is the data loss this phase exists to
    prevent. A caller that wants retry semantics re-reads the document,
    re-applies its change to the fresh state, and saves again — wrapping
    this error itself.

    See ``specs/004-write-correctness/design.md``.
    """

    def __init__(
        self,
        *args: object,
        doc_id: str,
        attempted_rev: str,
        reason: str = "",
    ) -> None:
        self.doc_id = doc_id
        self.attempted_rev = attempted_rev
        self.reason = reason
        super().__init__(*args)

    def __str__(self) -> str:
        return (
            f"Revision conflict for {self.doc_id}: "
            f"attempted rev={self.attempted_rev!r}, reason={self.reason!r}"
        )
