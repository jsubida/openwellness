"""AIP-160 ``filter=`` query parsing — minimum viable subset.

v1 supports only ``field=value`` clauses joined by ``AND``. Anything else
(``>``, ``OR``, function calls, parentheses, ``:`` for has-substring) is
rejected with a clear 400 message rather than silently misinterpreted.

This lets clients depend on a small, documented surface today and lets us
grow into the full CEL-like AIP-160 grammar later without breaking
existing requests.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from fastapi import HTTPException


def _bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": message,
                "details": [],
            }
        },
    )


# Operators / tokens we explicitly reject so users see a clear message rather
# than silent mis-parsing.
_UNSUPPORTED_TOKENS = {">", "<", ">=", "<=", "!=", ":", "(", ")"}


def parse_filter(
    expr: str | None,
    *,
    allowed_fields: Mapping[str, Callable[[str], Any]],
) -> dict[str, Any]:
    """Parse a ``filter=`` expression into a mapping of field→coerced value.

    ``allowed_fields`` maps each filterable field name to a coercion
    callable (``int``, ``str``, ``float``, ``lambda v: v == "true"``,
    etc.). Fields not in the map are rejected; mis-typed values raise 400.

    An empty / ``None`` ``expr`` returns ``{}``.
    """
    if expr is None or expr.strip() == "":
        return {}

    # Cheap rejection of unsupported operators. We split before parsing
    # so a ``foo>3`` filter fails fast with a useful message.
    for token in _UNSUPPORTED_TOKENS:
        if token in expr:
            raise _bad_request(
                f"filter operator {token!r} is not supported; "
                f"v1 supports only 'field=value' clauses joined by AND"
            )

    # ``AND`` is case-insensitive in AIP-160, but for the limited grammar
    # we accept only uppercase to keep parsing trivial.
    clauses = [c.strip() for c in expr.split(" AND ")]
    if any(" or " in c.lower() for c in clauses):
        raise _bad_request(
            "filter 'OR' is not supported; v1 supports only 'field=value' "
            "clauses joined by AND"
        )

    out: dict[str, Any] = {}
    for clause in clauses:
        if "=" not in clause:
            raise _bad_request(
                f"filter clause {clause!r} is malformed; expected 'field=value'"
            )
        field, _, raw = clause.partition("=")
        field = field.strip()
        raw = raw.strip().strip('"').strip("'")

        if field not in allowed_fields:
            raise _bad_request(
                f"filter field {field!r} is not filterable on this resource"
            )
        try:
            out[field] = allowed_fields[field](raw)
        except (ValueError, TypeError) as e:
            raise _bad_request(
                f"filter value for {field!r} is invalid: {e}"
            ) from e
    return out
