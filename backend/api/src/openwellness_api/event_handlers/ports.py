"""Ports for the event-handler routes: reads and publishing only (D-02).

Handlers never write. Every write belongs to an enqueued job, so the ports
here expose the two read-only lookups frame performs to choose a task and
the publisher that hands the task to Celery (D-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.requests import Request

from .legacy_studies import LegacyStudyIdsProvider


class ComponentSettingsReader(Protocol):
    """Frame's ``StudyComponentSetting.fetchIn(...)[0]``."""

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        """Return the oldest setting for ``(study_id, component_type)``.

        ``None`` means zero rows (frame's 412 path).
        """
        ...


class StudyReader(Protocol):
    """Frame's ``Study.findById``."""

    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        """Return the study document, or ``None`` when it does not exist.

        Raises on an id that cannot be an ObjectId, as Mongoose's cast does.
        """
        ...


class ConditionReader(Protocol):
    """Frame's ``Condition.fetchLatest(owner)`` (SMART weight, D-04)."""

    def latest(self, owner: object) -> dict[str, Any] | None:
        """Return the owner's latest Condition document, or ``None``."""
        ...


class ParticipantReader(Protocol):
    """Frame's ``Participant`` lookups on the ``participants`` collection."""

    def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
        """``Participant.findByCouchId`` (SMART weight, D-04), or ``None``."""
        ...

    def find_by_id(self, participant_id: object) -> dict[str, Any] | None:
        """``Participant.findById(new ObjectID(pid))`` (ActiGraph, HOOK-02).

        ``None`` for an unknown or absent id; raises on a malformed id.
        """
        ...


class DeviceReader(Protocol):
    """Frame's ``Device.find({serialNumber})[0]`` (ActiGraph, HOOK-02)."""

    def first_by_serial_number(self, serial_number: str) -> dict[str, Any] | None:
        """Return the first ``devices`` document with that serial, or ``None``."""
        ...


class TaskPublisher(Protocol):
    """Hands one task, by name, to the broker frame's workers consume."""

    def publish(self, task_name: str, args: list[Any]) -> None:
        """Publish ``task_name(*args)``. Raises :class:`TaskPublishError`."""
        ...


class TaskPublishError(Exception):
    """A task could not be handed to the broker.

    The message never carries task arguments (HIPAA log retention).
    """


class _NotWiredConditions:
    """Default until the lifespan wires a real reader: loud, never a skip."""

    def latest(self, owner: object) -> dict[str, Any] | None:
        raise RuntimeError("ConditionReader not wired")


class _NotWiredParticipants:
    """Default until the lifespan wires a real reader: loud, never a skip."""

    def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
        raise RuntimeError("ParticipantReader not wired")

    def find_by_id(self, participant_id: object) -> dict[str, Any] | None:
        raise RuntimeError("ParticipantReader not wired")


class _NotWiredDevices:
    """Default until the lifespan wires a real reader: loud, never a skip."""

    def first_by_serial_number(self, serial_number: str) -> dict[str, Any] | None:
        raise RuntimeError("DeviceReader not wired")


@dataclass(frozen=True)
class EventHandlerDeps:
    """Everything an event-handler route may touch.

    Later plans add fields with defaults; no field may offer a write.
    """

    settings: ComponentSettingsReader
    studies: StudyReader
    publisher: TaskPublisher
    # ``STUDY_SPECIFIC``'s legacy ids, parsed on first use: an absent or
    # unparseable key is a hapi 500 on the routes that need it, never a
    # boot failure and never a guess that a study is non-legacy (D-03).
    legacy_studies: LegacyStudyIdsProvider = field(
        default_factory=LegacyStudyIdsProvider.from_process_env
    )
    # The SMART weight reads (D-04). An un-wired default raises, so a
    # production path missing them is a hapi 500, never a silent 204.
    conditions: ConditionReader = field(default_factory=_NotWiredConditions)
    participants: ParticipantReader = field(default_factory=_NotWiredParticipants)
    # The ActiGraph device lookup (HOOK-02); loud when un-wired, as above.
    devices: DeviceReader = field(default_factory=_NotWiredDevices)


def get_event_handler_deps(request: Request) -> EventHandlerDeps:
    """Read the deps installed on ``app.state``.

    Called inside the handler's own ``try`` (not via ``Depends``), so a
    missing attribute becomes a hapi 500 rather than Starlette's plain-text 500.
    """
    deps = request.app.state.event_handler_deps
    if not isinstance(deps, EventHandlerDeps):
        raise TypeError("app.state.event_handler_deps is not EventHandlerDeps")
    return deps
