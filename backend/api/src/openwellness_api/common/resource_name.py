"""AIP-122 resource name formatting / parsing.

Resource names take the form ``collection/{id}`` for top-level resources,
or ``parent/{pid}/collection/{id}`` for resources nested under a parent.
Format and parse helpers live here so that callers never hand-assemble
slash-separated strings.
"""

from __future__ import annotations


def format_name(
    *,
    collection: str,
    id_: str,
    parent: str | None = None,
) -> str:
    """Return the canonical AIP resource name.

    ``parent`` is itself a resource name (``"users/abc"``); the resulting
    name is ``"users/abc/weights/xyz"``. For top-level resources, pass
    ``parent=None``: result is ``"users/abc"``.
    """
    if parent:
        return f"{parent}/{collection}/{id_}"
    return f"{collection}/{id_}"


def parse_name(name: str) -> dict[str, str]:
    """Inverse of :func:`format_name`.

    ``"users/abc/weights/xyz"`` parses to ``{"users": "abc", "weights": "xyz"}``.
    Raises ``ValueError`` if the structure is not an even ``segment/id`` repetition.
    """
    parts = name.split("/")
    if not parts or len(parts) % 2 != 0:
        raise ValueError(f"invalid resource name: {name!r}")
    return {parts[i]: parts[i + 1] for i in range(0, len(parts), 2)}
