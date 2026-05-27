"""AIP-142 timestamp conversion.

Domain entities store ``created_at`` / ``updated_at`` as epoch floats
(``time.time()`` semantics). On the wire, AIP-142 requires RFC-3339
strings. These helpers do the boundary conversion in both directions.
"""

from __future__ import annotations

from datetime import datetime, timezone


def epoch_to_rfc3339(seconds: float | int | None) -> str | None:
    """Convert an epoch-second value to an RFC-3339 string in UTC.

    Returns ``None`` if ``seconds`` is ``None``. Sub-second precision is
    preserved with microseconds; the trailing ``+00:00`` is replaced with
    ``Z`` per RFC-3339 / AIP-142 convention.
    """
    if seconds is None:
        return None
    dt = datetime.fromtimestamp(float(seconds), tz=timezone.utc)
    iso = dt.isoformat(timespec="microseconds")
    return iso.replace("+00:00", "Z")


def rfc3339_to_epoch(value: str | None) -> float | None:
    """Parse an RFC-3339 string into epoch seconds."""
    if value is None or value == "":
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(text).timestamp()
