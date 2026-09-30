"""Deployed-graph self-check for Google Health in ``ow_api`` (opserver Phase 10.1).

Run inside the built image (10.1-09, 10.1-13)::

    python -m openwellness_api.google_health.selfcheck

It builds the real objects from the environment, the way the lifespan does,
and runs six checks in order, printing one line each:

- ``settings``: every ``GOOGLE_HEALTH_*`` key set and every rule of
  :meth:`GoogleHealthSettings.problems` satisfied (against
  ``API_AUTH_JWT_SECRET``);
- ``signature_vector``: the real :class:`TinkSignatureVerifier` accepts the
  bundled openssl-signed vector and rejects it over a tampered body;
- ``keyset_snapshot``: the bundled snapshot of Google's keyset parses into at
  least one P-256 key through the verifier's parser;
- ``token_roundtrip``: a link and a state token mint and verify against the
  real Redis client (the state nonce is consumed again);
- ``redis_ping``: Redis (``REDIS_URL``) answers;
- ``publisher_config``: ``CELERY_BROKER_URL`` is set and the producer app
  builds (nothing is published).

Output is ``PASS <name>`` or ``FAIL <name>[: <names>]`` where ``<names>`` are
setting or rule names, or an exception class name, never a value. Exit 0 only
when every check passes. The network is not used for the keyset: the verifier
is fed the bundled files.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from collections.abc import Callable
from importlib import resources
from typing import Any, Final

from ..config import AuthSettings, RedisSettings
from ..event_handlers.celery_producer import (
    ROUTER_QUEUE,
    CeleryTaskPublisher,
    ProducerSettings,
)
from .settings import GoogleHealthSettings
from .signature import TinkSignatureVerifier, parse_keyset
from .tokens import GoogleHealthTokens

CHECKS: Final[tuple[str, ...]] = (
    "settings",
    "signature_vector",
    "keyset_snapshot",
    "token_roundtrip",
    "redis_ping",
    "publisher_config",
)
_SELFCHECK_PARTICIPANT: Final = "000000000000000000000000"


class CheckFailed(Exception):
    """A check failed for a reason already reduced to names (safe to print)."""


def _data(name: str) -> str:
    return resources.files(__package__).joinpath("data", name).read_text("utf-8")


def _check_settings(settings: GoogleHealthSettings) -> None:
    findings = [*settings.missing_keys(), *settings.problems(AuthSettings().jwt_secret)]
    if findings:
        raise CheckFailed(", ".join(findings))


def _check_signature_vector() -> None:
    vector = json.loads(_data("selfcheck_vector.json"))
    keyset = json.dumps(vector["keyset"])
    verifier = TinkSignatureVerifier(fetch=lambda: keyset)
    body = vector["body"].encode("utf-8")
    if verifier.verify(vector["signature"], body) is not True:
        raise CheckFailed("vector_rejected")
    if verifier.verify(vector["signature"], body + b" ") is not False:
        raise CheckFailed("tampered_vector_accepted")


def _check_keyset_snapshot() -> None:
    parsed = parse_keyset(_data("webhooks_public_keyset.json"))
    if not any(key.curve == "NIST_P256" and key.hash == "SHA256" for key in parsed.keys):
        raise CheckFailed("no_p256_key")


def _check_token_roundtrip(settings: GoogleHealthSettings, redis: Any) -> None:
    tokens = GoogleHealthTokens(settings, redis)
    link, exp = tokens.mint_link(_SELFCHECK_PARTICIPANT)
    claims = tokens.verify_link(link)
    if claims.participant_id != _SELFCHECK_PARTICIPANT:
        raise CheckFailed("link_mismatch")
    browser_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    state = tokens.mint_state(_SELFCHECK_PARTICIPANT, claims.jti, exp, browser_hash)
    consumed = tokens.consume_state(state, browser_hash)
    if consumed.participant_id != _SELFCHECK_PARTICIPANT or consumed.link_jti != claims.jti:
        raise CheckFailed("state_mismatch")


def _check_redis_ping(redis: Any) -> None:
    if not redis.ping():
        raise CheckFailed("no_pong")


def _check_publisher_config() -> None:
    producer_settings = ProducerSettings()
    if not producer_settings.broker_url:
        raise CheckFailed("CELERY_BROKER_URL")
    app = CeleryTaskPublisher(producer_settings).app
    if app.conf.task_default_queue != ROUTER_QUEUE or app.conf.task_serializer != "json":
        raise CheckFailed("producer_conf")


def _run(name: str, check: Callable[[], None]) -> bool:
    try:
        check()
    except CheckFailed as exc:
        print(f"FAIL {name}: {exc}")
        return False
    except Exception as exc:  # any failure, reported by class name only
        print(f"FAIL {name}: {type(exc).__name__}")
        return False
    print(f"PASS {name}")
    return True


def main(redis_client: Any = None) -> int:
    """Run every check; 0 when all pass, else 1. ``redis_client`` is for tests."""
    settings = GoogleHealthSettings()
    if redis_client is None:
        from ..deps.auth_container import _make_redis_client

        redis_client = _make_redis_client(RedisSettings())
    checks: dict[str, Callable[[], None]] = {
        "settings": lambda: _check_settings(settings),
        "signature_vector": _check_signature_vector,
        "keyset_snapshot": _check_keyset_snapshot,
        "token_roundtrip": lambda: _check_token_roundtrip(settings, redis_client),
        "redis_ping": lambda: _check_redis_ping(redis_client),
        "publisher_config": _check_publisher_config,
    }
    results = [_run(name, checks[name]) for name in CHECKS]
    sys.stdout.flush()
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
