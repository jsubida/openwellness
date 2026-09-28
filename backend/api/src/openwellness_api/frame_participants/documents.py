"""Frame-shaped documents for ``POST /api/participants``. Pure: no I/O, no HTTP.

Everything here reproduces what frame (``api/server/api/participants.js``,
``models/mongoose/participant.js``, ``models/user.js``) validates and writes,
so the documents ow writes are indistinguishable to frame and the scheduler
from the ones frame writes.

* :func:`validate_create_payload` is the route's Joi 17 schema under hapi's
  defaults (``convert``, ``abortEarly``, unknown keys refused). It is pinned by
  ``tests/fixtures/frame_participant_joi_matrix.json``, whose verdicts and
  converted values were produced by frame's own Joi on frame's own schema.
  One approximation is deliberate: Joi's ``email()`` checks the TLD against
  the IANA list; here syntax goes through ``email-validator`` with
  deliverability off, which rejects the reserved/special-use TLDs but accepts
  an unregistered one.
* :func:`build_participant_doc` is ``new Participant(obj)`` under Mongoose 7:
  ObjectId ``_id``/``studyId``/``assignedCoachId`` (research Pitfall 7: string
  ids are invisible to frame's ObjectId queries), every schema path that has a
  default, ``__v: 0``, and none of the payload keys the schema does not
  declare (``username``, ``password``, ``email``, ``location``, ``id``).
* :func:`build_user_doc` is ``User.create``: mongo-models validates the
  object against the users Joi schema, which adds ``roles: {}``,
  ``timeCreated`` and ``verifiedId: ''``.
* :func:`hash_password` is node ``bcrypt`` 5 (``genSalt(10)``, ``$2b$``):
  UTF-8 bytes truncated to 72, which node bcrypt does and pyca ``bcrypt`` 5
  refuses to do implicitly. Verified in the frame container with node
  ``bcrypt.compare`` (Assumption A9: participants sign in through frame).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import bcrypt
from bson import ObjectId
from email_validator import EmailNotValidError, validate_email


class ParticipantValidationError(ValueError):
    """The payload fails frame's Joi schema. The message names the Joi rule
    and the key only, never the value."""


# JavaScript Number.MAX_SAFE_INTEGER; Joi refuses numbers outside it.
_MAX_SAFE: Final = 2**53 - 1
# Joi 17 number coercion from a string (lib/types/number.js numberRx).
_NUMBER_RX: Final = re.compile(
    r"^\s*[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:e([+-]?\d+))?\s*$", re.IGNORECASE
)
# Joi string().token(): /^\w+$/ in JavaScript, i.e. ASCII only.
_TOKEN_RX: Final = re.compile(r"[A-Za-z0-9_]+")
_LONE_SURROGATE: Final = re.compile("[\ud800-\udfff]")

BCRYPT_ROUNDS: Final = 10
BCRYPT_MAX_BYTES: Final = 72


@dataclass(frozen=True)
class _Field:
    kind: str  # "string" | "number" | "array"
    required: bool = False
    default: Any = None
    has_default: bool = False
    allow: tuple[Any, ...] = ()
    length: int | None = None
    token: bool = False
    lowercase: bool = False
    email: bool = False
    integer: bool = False
    valid: tuple[Any, ...] = ()


# Key order is frame's schema order, which is Joi's validation order.
_SCHEMA: Final[dict[str, _Field]] = {
    "studyId": _Field("string", required=True, length=24),
    "username": _Field("string", required=True, token=True, lowercase=True),
    "password": _Field("string", required=True),
    "email": _Field("string", required=True, email=True, lowercase=True),
    "location": _Field("string", default="", has_default=True),
    "assignedCoachId": _Field("string"),
    "participantNumber": _Field("string", required=True),
    "participantType": _Field("number", default=0, has_default=True),
    "heightInInches": _Field("number", default=0, has_default=True),
    "participantStates": _Field("array", default=[], has_default=True),
    "tz": _Field("string", allow=(None, "")),
    "startWeight": _Field("number"),
    "age": _Field("number", allow=(None,)),
    "gender": _Field("number", integer=True, valid=(0, 1)),
    "id": _Field("string", length=24),
}


def _js_length(value: str) -> int:
    """String length in UTF-16 code units, as JavaScript counts it."""
    return len(value.encode("utf-16-le", "surrogatepass")) // 2


def _fail(key: str, rule: str) -> ParticipantValidationError:
    return ParticipantValidationError(f"{key}: {rule}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _to_number(key: str, value: Any) -> int | float:
    if isinstance(value, str):
        if not _NUMBER_RX.match(value):
            raise _fail(key, "number.base")
        number = float(value.strip())
        if number.is_integer():
            if abs(number) > _MAX_SAFE:
                raise _fail(key, "number.unsafe")
            return int(number)
        return number
    if not _is_number(value):
        raise _fail(key, "number.base")
    if isinstance(value, float) and not math.isfinite(value):
        raise _fail(key, "number.infinity")
    if abs(value) > _MAX_SAFE:
        raise _fail(key, "number.unsafe")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _check_string(key: str, spec: _Field, value: Any) -> str:
    if not isinstance(value, str):
        raise _fail(key, "string.base")
    if value == "":
        raise _fail(key, "string.empty")
    if spec.length is not None and _js_length(value) != spec.length:
        raise _fail(key, "string.min" if _js_length(value) < spec.length else "string.max")
    if spec.token and not _TOKEN_RX.fullmatch(value):
        raise _fail(key, "string.token")
    if spec.email:
        try:
            validate_email(value, check_deliverability=False)
        except EmailNotValidError:
            raise _fail(key, "string.email") from None
    return value.lower() if spec.lowercase else value


def _check(key: str, spec: _Field, value: Any) -> Any:
    if spec.allow and any(value is a or (a is not None and value == a and type(value) is type(a)) for a in spec.allow):
        return value
    if spec.kind == "string":
        return _check_string(key, spec, value)
    if spec.kind == "number":
        number = _to_number(key, value)
        if spec.valid and number not in spec.valid:
            raise _fail(key, "any.only")
        if spec.integer and not float(number).is_integer():
            raise _fail(key, "number.integer")
        return number
    if not isinstance(value, list):
        raise _fail(key, "array.base")
    for item in value:
        if not isinstance(item, str):
            raise _fail(key, "string.base")
        if item == "":
            raise _fail(key, "string.empty")
    return list(value)


def validate_create_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize the way hapi's Joi 17 does for frame's route.

    Returns the converted payload: ``username``/``email`` lowercased, numeric
    strings converted, and the defaults ``location=''``,
    ``participantType=0``, ``heightInInches=0``, ``participantStates=[]``.
    """
    if not isinstance(payload, dict):
        raise ParticipantValidationError("object.base")
    for key in payload:
        if key not in _SCHEMA:
            raise ParticipantValidationError("object.unknown")
    out: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        if key not in payload:
            if spec.required:
                raise _fail(key, "any.required")
            if spec.has_default:
                out[key] = list(spec.default) if isinstance(spec.default, list) else spec.default
            continue
        out[key] = _check(key, spec, payload[key])
    return out


def is_object_id(value: Any) -> bool:
    return isinstance(value, str) and ObjectId.is_valid(value) and len(value) == 24


def build_participant_doc(
    payload: dict[str, Any], pid: ObjectId, study_oid: ObjectId, now: datetime
) -> dict[str, Any]:
    """The document ``Participant.create`` inserts for a validated payload.

    Mongoose writes every schema path that has a default; paths without one
    (``userId``, ``assignedCoachId``, ``tz``, ``buddyId``, ``mastodon*``)
    appear only when supplied. Raises ``ValueError`` for an
    ``assignedCoachId`` Mongoose could not cast, and for a
    ``participantNumber`` that trims to nothing (frame fails ``linkParticipant``'s
    assertion on it), so neither ever reaches a write.
    """
    participant_number = payload["participantNumber"].strip()
    if not participant_number:
        raise ValueError("participantNumber is empty after trimming")
    doc: dict[str, Any] = {
        "_id": pid,
        "studyId": study_oid,
        "couchId": str(pid),
        "isActive": True,
        "isDropped": False,
    }
    if "assignedCoachId" in payload:
        if not is_object_id(payload["assignedCoachId"]):
            raise ValueError("assignedCoachId is not an ObjectId")
        doc["assignedCoachId"] = ObjectId(payload["assignedCoachId"])
    doc.update(
        {
            "googleId": None,
            "deviceId": None,
            "participantNumber": participant_number,
            "user": None,
            "couchbaseUser": None,
            "condition": None,
            "settings": None,
            "study": None,
            "coach": None,
            "assessmentWeight": None,
            "startWeight": payload.get("startWeight"),
            "participantType": payload.get("participantType", 0),
            "heightInInches": payload.get("heightInInches", 0),
            "participantStates": list(payload.get("participantStates", [])),
        }
    )
    if "tz" in payload:
        doc["tz"] = payload["tz"]
    doc["age"] = payload.get("age")
    doc["gender"] = payload.get("gender")
    # Mongoose applies the Date.now default after the other paths, so the
    # stored key order ends ..., age, gender, timeCreated, __v.
    doc["timeCreated"] = _ms(now)
    doc["__v"] = 0
    return doc


def build_user_doc(
    payload: dict[str, Any], now: datetime, user_id: ObjectId | None = None
) -> dict[str, Any]:
    """The document ``User.create`` inserts: bcrypt hash, ``isActive`` true,
    and the users Joi defaults (``roles: {}``, ``timeCreated``,
    ``verifiedId: ''``). ``timeCreated`` is the real creation time."""
    return {
        "_id": user_id if user_id is not None else ObjectId(),
        "email": payload["email"].lower(),
        "isActive": True,
        "password": hash_password(payload["password"]),
        "username": payload["username"].lower(),
        "location": payload.get("location", ""),
        "roles": {},
        "timeCreated": _ms(now),
        "verifiedId": "",
    }


def password_bytes(password: str) -> bytes:
    """The bytes node ``bcrypt`` hashes: UTF-8 (a lone surrogate becomes
    U+FFFD, as Node encodes it), truncated to 72 bytes."""
    text = _LONE_SURROGATE.sub("�", password)
    return text.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """``bcrypt.hash(password, await bcrypt.genSalt(10))`` as node computes it."""
    return bcrypt.hashpw(password_bytes(password), bcrypt.gensalt(BCRYPT_ROUNDS, prefix=b"2b")).decode(
        "ascii"
    )


def _ms(moment: datetime) -> datetime:
    """Truncate to milliseconds, BSON's date precision, in UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.replace(microsecond=(moment.microsecond // 1000) * 1000)


def _js_date(moment: datetime) -> str:
    """``Date.prototype.toJSON``: ``YYYY-MM-DDTHH:MM:SS.mmmZ`` in UTC."""
    moment = _ms(moment)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _encode(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return _js_date(value)
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def participant_response(participant_doc: dict[str, Any], user_doc: dict[str, Any]) -> dict[str, Any]:
    """Frame's 200 body: the participant as Mongoose's ``toJSON`` renders it,
    with ``user`` set to the stored users document after the link.

    D-11 parity: frame's response carries ``user.password``, the bcrypt hash
    (``GET /participants/{id}`` deletes it; this route does not). Research
    Open Question 5 recommends stripping it; that is flagged to the user and
    NOT decided here, so the hash is returned as frame returns it.
    """
    body = _encode(participant_doc)
    body["user"] = _encode(user_doc)
    return body
