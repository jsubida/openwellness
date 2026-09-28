"""Tests for the Celery producer behind the event-handler publisher port.

HOOK-01, D-01: frame's event handlers enqueue by task name onto the Redis
``celery`` list that ``router`` consumes (``celery ... worker -Q celery``).
``CeleryTaskPublisher`` is the ``TaskPublisher`` that reproduces that hop with
Celery's own ``send_task`` (protocol 2, JSON), so no message is hand-rolled.

The contract proven here:

- the message lands on queue ``celery`` with the task name in its headers,
  JSON content and the exact positional args (``None`` included);
- an unreachable broker fails fast as ``TaskPublishError`` (the route turns it
  into a hapi 500, never a silent 204; research Pitfall 1);
- an unset ``CELERY_BROKER_URL`` never blocks construction (``ow_api`` still
  boots) and fails only at publish time, naming the missing key;
- the broker key is opserver's shared ``CELERY_BROKER_URL``, never an ``OW_``
  copy that could drift to a Redis no worker reads (research Pitfall 9);
- error messages carry the exception class name, never task arguments
  (HIPAA 6-year log retention).
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from kombu.transport import memory

from openwellness_api.event_handlers import celery_producer
from openwellness_api.event_handlers.celery_producer import (
    CeleryTaskPublisher,
    ProducerSettings,
)
from openwellness_api.event_handlers.ports import TaskPublishError, TaskPublisher

OWNER_SENTINEL = "owner-sentinel-7f3a9c"


@pytest.fixture(autouse=True)
def _isolated_broker_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the host's broker env out of every test.

    Celery itself prefers ``os.environ['CELERY_BROKER_URL']`` over configured
    ``broker_url``, so a stray value would silently redirect these tests.
    """
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("OW_CELERY_BROKER_URL", raising=False)
    memory.Channel.queues.clear()


def _publisher(broker_url: str) -> CeleryTaskPublisher:
    return CeleryTaskPublisher(ProducerSettings(broker_url=broker_url))


def _drain(publisher: CeleryTaskPublisher, queue: str = "celery") -> list[Any]:
    """Read every message on ``queue`` through the publisher's own app."""
    messages: list[Any] = []
    with publisher.app.connection_for_read() as conn:
        simple = conn.SimpleQueue(queue)
        try:
            while True:
                try:
                    message = simple.get_nowait()
                except simple.Empty:
                    break
                message.ack()
                messages.append(message)
        finally:
            simple.close()
    return messages


def test_publisher_satisfies_the_port() -> None:
    publisher: TaskPublisher = _publisher("memory://")
    assert callable(publisher.publish)


def test_memory_broker_message_is_protocol_2_json_on_celery_queue() -> None:
    publisher = _publisher("memory://")

    publisher.publish("jobs.sandbox.sayWee", ["a", None])

    messages = _drain(publisher)
    assert len(messages) == 1
    message = messages[0]
    # Protocol 2 carries the task name and id in the headers, not the body.
    assert message.headers["task"] == "jobs.sandbox.sayWee"
    assert message.headers["id"]
    assert message.content_type == "application/json"
    args, kwargs, _embed = message.decode()
    assert args == ["a", None]
    assert kwargs == {}
    assert message.delivery_info["routing_key"] == "celery"


def test_producer_app_configuration_matches_the_router_contract() -> None:
    publisher = _publisher("memory://")
    conf = publisher.app.conf

    assert publisher.app.main == "openwellness_api_producer"
    assert conf.task_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.task_default_queue == "celery"
    assert conf.task_protocol == 2
    assert conf.broker_connection_timeout == 2
    assert conf.broker_transport_options["socket_connect_timeout"] == 2
    assert conf.broker_transport_options["socket_timeout"] == 2
    assert conf.task_publish_retry is True
    assert conf.task_publish_retry_policy == {
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.5,
    }
    assert conf.result_backend is None


def test_unreachable_broker_raises_task_publish_error_fast() -> None:
    publisher = _publisher("redis://127.0.0.1:1/0")

    started = time.monotonic()
    with pytest.raises(TaskPublishError) as excinfo:
        publisher.publish("jobs.sandbox.sayWee", [OWNER_SENTINEL])
    elapsed = time.monotonic() - started

    assert elapsed < 6, f"publish took {elapsed:.2f}s against an unreachable broker"
    assert OWNER_SENTINEL not in str(excinfo.value)


def test_unset_broker_url_constructs_and_fails_only_at_publish() -> None:
    settings = ProducerSettings()
    assert settings.broker_url == ""

    publisher = CeleryTaskPublisher(settings)  # must not raise: ow_api still boots

    with pytest.raises(TaskPublishError) as excinfo:
        publisher.publish("jobs.sandbox.sayWee", [OWNER_SENTINEL])
    assert "CELERY_BROKER_URL" in str(excinfo.value)
    assert OWNER_SENTINEL not in str(excinfo.value)


def test_settings_read_the_shared_celery_broker_url_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OW_CELERY_BROKER_URL", "redis://wrong:6379/9")
    assert ProducerSettings().broker_url == ""

    monkeypatch.setenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    assert ProducerSettings().broker_url == "redis://redis:6379/0"


def test_send_failure_keeps_class_name_and_drops_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = _publisher("memory://")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(f"cannot publish {OWNER_SENTINEL}")

    monkeypatch.setattr(publisher.app, "send_task", _boom)

    with pytest.raises(TaskPublishError) as excinfo:
        publisher.publish("jobs.sandbox.sayWee", [OWNER_SENTINEL])
    assert "RuntimeError" in str(excinfo.value)
    assert OWNER_SENTINEL not in str(excinfo.value)


def test_concurrent_publishes_succeed_and_build_the_app_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds: list[str] = []
    real_celery = celery_producer.Celery

    def _counting_celery(*args: Any, **kwargs: Any) -> Any:
        builds.append("built")
        # Widen the race window so an unlocked lazy build would double up.
        time.sleep(0.05)
        return real_celery(*args, **kwargs)

    monkeypatch.setattr(celery_producer, "Celery", _counting_celery)
    publisher = _publisher("memory://")

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def _worker(owner: str) -> None:
        try:
            barrier.wait(timeout=5)
            publisher.publish("jobs.sandbox.sayWee", [owner])
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(f"o{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert builds == ["built"]
    owners = sorted(message.decode()[0][0] for message in _drain(publisher))
    assert owners == ["o0", "o1"]
