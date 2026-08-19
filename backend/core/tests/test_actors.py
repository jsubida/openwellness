"""The machine-actor helper builds one namespaced shape and rejects the rest.

Why this module exists at all: every repository write now names the identity
that performed it (D-15), and a scheduled job has no human identity to name.
If each job spelled its own value, `spring` would accumulate audit fields that
are indistinguishable from participant ids — a machine write could be read
back as a coach's edit, and nothing in the data would say otherwise. One
construction point with a reserved prefix is what makes the distinction
checkable rather than conventional (D-14).

The rejection cases matter as much as the happy path. A bare prefix produced
from an empty job name looks deliberate in an audit trail while carrying no
information, which is worse than the defect it replaces.

RED → these fail before `application/actors.py` exists.
GREEN → they pass once it does.
"""

import pytest

from openwellness_core.application.actors import (
    SYSTEM_ACTOR_PREFIX,
    InvalidActorError,
    is_system_actor,
    system_actor,
)

# Shaped like a real Mongo `_id` hex string, because that is what a human
# principal id actually looks like coming out of `backend/api`'s auth layer.
HUMAN_PRINCIPAL_ID = "5988f5bebd8d334a5196c93c"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_system_actor_prefixes_the_job_name():
    """The built value is the job name behind the reserved namespace."""
    assert system_actor("fitbit_sync") == f"{SYSTEM_ACTOR_PREFIX}fitbit_sync"


def test_the_prefix_constant_carries_its_own_separator():
    """Callers never spell the separator, so it cannot drift between sites."""
    assert SYSTEM_ACTOR_PREFIX == "system:"
    assert system_actor("x").startswith(SYSTEM_ACTOR_PREFIX)


def test_a_built_machine_actor_is_recognized_as_one():
    """Build and recognize are two halves of one contract; assert the round trip."""
    assert is_system_actor(system_actor("fitbit_sync"))


def test_system_actor_is_idempotent_under_re_prefixing():
    """Re-building an already-built value must not double the namespace.

    Call sites pass values through helpers and configuration; a doubled
    `system:system:` prefix would still *look* namespaced while breaking any
    equality check against the job's own name.
    """
    once = system_actor("fitbit_sync")

    assert system_actor(once) == once
    assert not once.removeprefix(SYSTEM_ACTOR_PREFIX).startswith(
        SYSTEM_ACTOR_PREFIX
    )


def test_surrounding_whitespace_is_stripped_from_the_job_name():
    """A trailing space would make two spellings of the same job unequal."""
    assert system_actor("  fitbit_sync  ") == system_actor("fitbit_sync")


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------


def test_an_empty_job_name_is_rejected():
    """A bare prefix carries no information but reads as intentional."""
    with pytest.raises(InvalidActorError):
        system_actor("")


def test_a_whitespace_only_job_name_is_rejected():
    """The same defect, one space away from passing a truthiness check."""
    with pytest.raises(InvalidActorError):
        system_actor("   ")


def test_a_bare_prefix_is_rejected_as_a_job_name():
    """`system:` on its own is the empty case wearing the namespace."""
    with pytest.raises(InvalidActorError):
        system_actor(SYSTEM_ACTOR_PREFIX)


def test_the_rejection_is_catchable_as_a_value_error():
    """Existing bad-input handlers keep working without importing this module."""
    with pytest.raises(ValueError):
        system_actor("")


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------


def test_a_human_principal_id_is_not_a_machine_actor():
    """The distinction the prefix exists to make, asserted on a real id shape."""
    assert not is_system_actor(HUMAN_PRINCIPAL_ID)


def test_an_empty_value_is_not_a_machine_actor():
    """An unattributed write must not be mistaken for a machine one."""
    assert not is_system_actor("")


def test_a_bare_prefix_is_not_a_machine_actor():
    """Recognition agrees with construction: `system:` alone names nobody."""
    assert not is_system_actor(SYSTEM_ACTOR_PREFIX)


def test_a_service_name_without_the_namespace_is_not_a_machine_actor():
    """The original defect's value — a bare service name — stays unrecognized."""
    assert not is_system_actor("scheduler")
