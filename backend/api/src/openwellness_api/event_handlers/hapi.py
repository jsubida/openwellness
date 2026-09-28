"""hapi-parity response helpers and JavaScript value semantics (D-05).

Frame answers the event-handler routes through hapi 21 with
``routes: { security: true, cors: true }``. Every value here is taken from
the responses captured live from frame (10-RESEARCH.md, "Captured frame
responses"), so a caller cannot tell which side answered.

Starlette notes the helpers depend on:

- ``JSONResponse`` defaults to ``application/json`` with no charset. hapi
  sends ``application/json; charset=utf-8``, so :func:`boom` sets the full
  media type explicitly.
- ``JSONResponse`` renders compact separators, matching ``JSON.stringify``.
- Starlette omits ``content-length`` on a 204 and sends ``content-length: 0``
  on an empty 200, matching hapi's ``return null`` and ``h.close`` only when
  no media type is set on those responses.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any, Final

from starlette.responses import JSONResponse, Response

JSON_UTF8: Final = "application/json; charset=utf-8"
HTML_UTF8: Final = "text/html; charset=utf-8"

# Verbatim from the captured frame responses. Omitted on the h.close path.
HAPI_HEADERS: Final[dict[str, str]] = {
    "vary": "origin",
    "access-control-expose-headers": "WWW-Authenticate,Server-Authorization",
    "strict-transport-security": "max-age=15768000",
    "x-frame-options": "DENY",
    "x-xss-protection": "0",
    "x-download-options": "noopen",
    "x-content-type-options": "nosniff",
    "cache-control": "no-cache",
}

# Node's http.STATUS_CODES phrases, which Boom copies into ``error``. Python's
# HTTPStatus phrases differ (413 in particular) and must not be used.
_REASON: Final[dict[int, str]] = {
    400: "Bad Request",
    404: "Not Found",
    412: "Precondition Failed",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    500: "Internal Server Error",
}

INVALID_JSON_MESSAGE: Final = "Invalid request payload JSON format"


class HapiReply(Exception):
    """Short-circuits a handler with a ready hapi response (a thrown Boom)."""

    def __init__(self, response: Response) -> None:
        super().__init__(response.status_code)
        self.response = response


def boom(status: int, message: str) -> JSONResponse:
    """A Boom error: ``{"statusCode","error","message"}`` in that key order."""
    return JSONResponse(
        {"statusCode": status, "error": _REASON[status], "message": message},
        status_code=status,
        headers=HAPI_HEADERS,
        media_type=JSON_UTF8,
    )


def internal() -> JSONResponse:
    """hapi's rendering of any uncaught handler error."""
    return boom(500, "An internal server error occurred")


def empty_null() -> Response:
    """Handler ``return null``: 204, no content-type, no content-length."""
    return Response(status_code=204, headers=HAPI_HEADERS)


def empty_string() -> Response:
    """Handler ``return ''``: 204 with ``text/html; charset=utf-8``."""
    return Response(status_code=204, media_type=HTML_UTF8, headers=HAPI_HEADERS)


def closed() -> Response:
    """Pre-method ``return h.close``: bare 200, empty body, no extra headers."""
    return Response(status_code=200)


# --------------------------------------------------------------------------- #
# Payload
# --------------------------------------------------------------------------- #


def _reject_constant(name: str) -> Any:
    # JSON.parse rejects NaN / Infinity / -Infinity; Python accepts them.
    raise ValueError(f"invalid JSON constant {name}")


def parse_json_payload(raw: bytes) -> Any:
    """Parse a request body the way hapi's JSON payload parser does.

    An empty body is hapi's ``null`` payload. Anything ``JSON.parse`` would
    reject raises :class:`HapiReply` carrying hapi's 400. Content-type
    handling is not modelled here.
    """
    if not raw:
        return None
    try:
        return json.loads(
            raw.decode("utf-8", errors="replace"), parse_constant=_reject_constant
        )
    except ValueError as exc:
        raise HapiReply(boom(400, INVALID_JSON_MESSAGE)) from exc


# --------------------------------------------------------------------------- #
# JavaScript value semantics
# --------------------------------------------------------------------------- #


class _Undefined:
    """JavaScript ``undefined``: a missing property, distinct from ``null``."""

    _instance: _Undefined | None = None

    def __new__(cls) -> _Undefined:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNDEFINED"

    def __bool__(self) -> bool:
        return False


UNDEFINED: Final[Any] = _Undefined()

_MAX_SAFE_INTEGER: Final = 2**53


def _js_number(x: float) -> str:
    """ECMAScript ``Number::toString`` for a double."""
    if math.isnan(x):
        return "NaN"
    if x == 0:
        return "0"  # includes -0
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x < 0:
        return "-" + _js_number(-x)
    # repr() is the shortest round-tripping digit string, as in JS.
    _, digit_tuple, exponent = Decimal(repr(x)).as_tuple()
    assert isinstance(exponent, int)
    digits = list(digit_tuple)
    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    s = "".join(str(d) for d in digits)
    k = len(s)
    n = exponent + k
    if k <= n <= 21:
        return s + "0" * (n - k)
    if 0 < n <= 21:
        return s[:n] + "." + s[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + s
    e = n - 1
    exp = ("+" if e >= 0 else "-") + str(abs(e))
    if k == 1:
        return s + "e" + exp
    return s[0] + "." + s[1:] + "e" + exp


def js_string(value: object) -> str:
    """JavaScript ``String(value)`` for JSON-shaped values.

    Used wherever frame builds a message by string concatenation, so the
    bytes of 412 bodies match (``'Study (' + studyId + ...``).
    """
    if value is UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        if abs(value) <= _MAX_SAFE_INTEGER:
            return str(value)
        try:
            return _js_number(float(value))  # JSON.parse yields a double
        except OverflowError:
            return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, float):
        return _js_number(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ",".join(
            "" if item is None or item is UNDEFINED else js_string(item)
            for item in value
        )
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def js_length(value: object) -> object:
    """JavaScript ``value.length`` for a non-null JSON value.

    Strings and arrays have a length; an object only through an own
    ``length`` key; numbers and booleans read ``undefined``.
    """
    if isinstance(value, (str, list, tuple)):
        return len(value)
    if isinstance(value, dict):
        return value.get("length", UNDEFINED)
    return UNDEFINED


def js_strict_equals_zero(value: object) -> bool:
    """JavaScript ``value === 0``."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == 0
    )
