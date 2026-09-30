"""Celery producer for the event-handler publisher port (D-01).

Frame's event handlers hand a task, by name, to the Redis ``celery`` list that
``router`` consumes (``celery -A router.app worker -Q celery``). Router then
forwards each name to the worker queue that owns it. This module reproduces
only that first hop, with Celery's own ``send_task`` (protocol 2, JSON). Router
runs Celery 5.6, which consumes protocol 2 natively, so no message is
hand-rolled and nothing downstream changes.

Design points:

- **Shared broker key.** The URL comes from opserver's ``CELERY_BROKER_URL``,
  the key ``router`` and frame already read. A service-prefixed copy could drift to a
  Redis no worker consumes, and that failure is silent (research Pitfall 9).
  Celery itself also prefers ``os.environ['CELERY_BROKER_URL']`` over the
  configured URL, so the two always agree.
- **Boot never depends on the broker.** The Celery app is built lazily on the
  first publish, and an unset URL fails only that publish. ``ow_api`` still
  starts and serves every other route.
- **Fail fast and loudly.** Tight connect/read timeouts and a short publish
  retry policy keep a dead broker well inside Sync Gateway's webhook budget.
  Every failure surfaces as :class:`TaskPublishError`, which the route turns
  into a hapi 500 so the caller sees it (never a silent 204).
- **No payload in errors.** A :class:`TaskPublishError` message carries the
  underlying exception's class name only, never task arguments (owner ids),
  because these logs are retained for six years (HIPAA).
- **No result backend.** Frame never reads results; neither does this.
"""

from __future__ import annotations

import math
import threading
from typing import Any

from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ports import TaskPublishError

PRODUCER_APP_NAME = "openwellness_api_producer"
ROUTER_QUEUE = "celery"
# The queue the new scheduler worker consumes. Must equal ``SCHEDULER_NEW`` in
# ``scheduler/router/task_router.py:14``: a typo publishes successfully to a
# queue no worker reads (D-06).
SCHEDULER_NEW_QUEUE = "scheduler_new"

_BROKER_TIMEOUT_SECONDS = 2
_PUBLISH_RETRY_POLICY: dict[str, float | int] = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}


class ProducerSettings(BaseSettings):
    """Broker settings, read from opserver's shared ``CELERY_BROKER_URL``."""

    model_config = SettingsConfigDict(env_prefix="CELERY_", extra="ignore")

    broker_url: str = ""


def build_producer_app(broker_url: str) -> Celery:
    """Build the producer-only Celery app (no tasks, no result backend)."""
    app = Celery(PRODUCER_APP_NAME, broker=broker_url, set_as_current=False)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_default_queue=ROUTER_QUEUE,
        broker_connection_timeout=_BROKER_TIMEOUT_SECONDS,
        broker_transport_options={
            "socket_connect_timeout": _BROKER_TIMEOUT_SECONDS,
            "socket_timeout": _BROKER_TIMEOUT_SECONDS,
        },
        task_publish_retry=True,
        task_publish_retry_policy=dict(_PUBLISH_RETRY_POLICY),
        result_backend=None,
    )
    return app


def _is_non_finite(value: Any) -> bool:
    return isinstance(value, float) and not math.isfinite(value)


def js_json_args(args: list[Any]) -> list[Any]:
    """Task arguments as ``JSON.stringify`` would write them.

    node-celery serializes frame's arguments with ``JSON.stringify``, which
    writes ``NaN`` and ``Infinity`` as ``null``; Kombu's JSON encoder writes
    ``Infinity``, which the worker reads back as a float. The payload parser
    yields ``inf`` for an overflowing literal such as ``1e400``, so every
    non-finite float, at any depth, becomes ``None`` here.

    Iterative, because a payload may nest far past Python's recursion limit.
    Arguments without a non-finite float are returned unchanged.
    """
    pending: list[Any] = [args]
    found = False
    while pending and not found:
        node = pending.pop()
        if isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
        else:
            found = _is_non_finite(node)
    if not found:
        return args

    root: list[Any] = []
    # Each entry: (source container, the copy being filled).
    stack: list[tuple[Any, Any]] = [(args, root)]
    while stack:
        source, target = stack.pop()
        items = source.items() if isinstance(source, dict) else enumerate(source)
        for key, value in items:
            if isinstance(value, (dict, list)):
                copy: Any = {} if isinstance(value, dict) else []
                stack.append((value, copy))
                value = copy
            elif _is_non_finite(value):
                value = None
            if isinstance(target, dict):
                target[key] = value
            else:
                target.append(value)
    return root


class CeleryTaskPublisher:
    """``TaskPublisher`` onto the ``celery`` queue ``router`` consumes.

    Safe to share across request threads: the app is built once under a lock,
    and Celery's producer pool serializes access to broker connections.
    """

    def __init__(self, settings: ProducerSettings) -> None:
        self._broker_url = settings.broker_url
        self._lock = threading.Lock()
        self._app: Celery | None = None

    @property
    def app(self) -> Celery:
        """The lazily built producer app (built at most once)."""
        if self._app is None:
            with self._lock:
                if self._app is None:
                    self._app = build_producer_app(self._broker_url)
        return self._app

    def publish(self, task_name: str, args: list[Any], queue: str = ROUTER_QUEUE) -> None:
        """Publish ``task_name(*args)`` to ``queue`` (default ``celery``).

        Raises :class:`TaskPublishError` on a missing broker URL or any broker
        failure. The message names the cause's class, never the arguments.
        """
        if not self._broker_url:
            raise TaskPublishError("CELERY_BROKER_URL is not set")
        try:
            self.app.send_task(task_name, args=js_json_args(list(args)), queue=queue)
        except Exception as exc:
            raise TaskPublishError(type(exc).__name__) from exc
