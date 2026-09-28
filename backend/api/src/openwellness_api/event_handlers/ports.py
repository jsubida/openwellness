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


class TaskPublisher(Protocol):
    """Hands one task, by name, to the broker frame's workers consume."""

    def publish(self, task_name: str, args: list[Any]) -> None:
        """Publish ``task_name(*args)``. Raises :class:`TaskPublishError`."""
        ...


class TaskPublishError(Exception):
    """A task could not be handed to the broker.

    The message never carries task arguments (HIPAA log retention).
    """


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


def get_event_handler_deps(request: Request) -> EventHandlerDeps:
    """Read the deps installed on ``app.state``.

    Called inside the handler's own ``try`` (not via ``Depends``), so a
    missing attribute becomes a hapi 500 rather than Starlette's plain-text 500.
    """
    deps = request.app.state.event_handler_deps
    if not isinstance(deps, EventHandlerDeps):
        raise TypeError("app.state.event_handler_deps is not EventHandlerDeps")
    return deps
