"""Construction and recognition of machine actors.

Every repository write names the identity that performed it (D-15). Human
writes carry the authenticated principal's id, passed through unchanged from
``backend/api``. Machine writes — scheduled jobs, webhook handlers, migrations
— have no principal, and this module is the single place their identity is
built.

The format decision (D-14):

- A machine actor is :data:`SYSTEM_ACTOR_PREFIX` followed by the job's name.
  The namespace is what makes a machine write impossible to mistake for a
  participant or coach id, and :func:`is_system_actor` makes that distinction
  checkable rather than a convention a reader has to know.
- A bare service name is **not** a valid actor. Unnamespaced, it is
  indistinguishable from any other user-supplied string, which is the shape
  the defect this phase closes actually had: the Couchbase driver stamped its
  own service name into the field that records who edited a document, so a
  coach's edit was attributed to the scheduler.
- Empty and whitespace-only job names raise rather than yielding a bare
  prefix. A ``system:`` with nothing after it looks deliberate in an audit
  trail while carrying no more information than the missing value it replaced.

Safety of the format was audited under D-16 and recorded in
``specs/004-write-correctness/design.md``: no consumer in ``api``, ``coachapp``
or ``scheduler`` resolves this field against a user record, and non-id-shaped
values already exist in production data today. Nothing breaks by writing a
prefixed value here.

There is deliberately no registry or enum of known job names. ``backend/scheduler``
has exactly one task today (``openwellness.count_study_participants``, a read),
so an enum would be structure with no members to justify it. The caller names
its own job.
"""

__all__ = [
    "SYSTEM_ACTOR_PREFIX",
    "InvalidActorError",
    "is_system_actor",
    "system_actor",
]

#: Reserved namespace for machine identities, separator included, so no call
#: site ever spells the separator itself.
SYSTEM_ACTOR_PREFIX = "system:"


class InvalidActorError(ValueError):
    """Raised when a machine actor cannot be built from the given job name.

    Subclasses :class:`ValueError` because it is a bad-input signal and
    callers that already handle bad input should not need to import this
    module to keep working. The distinct type exists so a test — or an API
    error mapping — can name this case specifically.
    """


def system_actor(job_name: str) -> str:
    """Build the machine actor for ``job_name``.

    Idempotent: a value that already carries the namespace is returned with a
    single prefix, never a doubled one. Call sites pass actors through
    configuration and helper layers, and ``system:system:job`` would still look
    namespaced while failing every equality check against the job's own name.

    Surrounding whitespace is stripped so two spellings of the same job do not
    produce two different audit values.

    Raises:
        InvalidActorError: if ``job_name`` is empty, whitespace-only, or the
            bare prefix — all three name nobody.
    """
    name = (job_name or "").strip()
    if name.startswith(SYSTEM_ACTOR_PREFIX):
        name = name[len(SYSTEM_ACTOR_PREFIX) :].strip()
    if not name:
        raise InvalidActorError(
            "A machine actor needs a job name; got "
            f"{job_name!r}. A bare {SYSTEM_ACTOR_PREFIX!r} records no more "
            "than an unattributed write does."
        )
    return f"{SYSTEM_ACTOR_PREFIX}{name}"


def is_system_actor(value: str) -> bool:
    """Return whether ``value`` is a machine actor built by :func:`system_actor`.

    The bare prefix is rejected here for the same reason it is rejected during
    construction: recognition and construction must agree, or a value this
    module refuses to build could still be accepted as one it did.
    """
    return bool(value) and value.startswith(SYSTEM_ACTOR_PREFIX) and bool(
        value[len(SYSTEM_ACTOR_PREFIX) :].strip()
    )
