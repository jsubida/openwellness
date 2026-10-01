"""``GOOGLE-HEALTH-API-SIGNATURE`` verification (10.1-07 Task 3, GHA-02).

Every signature here comes from ``fixtures/google_health_signature/vectors.json``,
which ``gen_vectors.sh`` produces with the ``openssl`` CLI (an implementation
independent of the verifier) plus stdlib framing: ``0x01 || key id || DER
ECDSA-SHA256``, and a Tink JSON public keyset for the openssl keys. No test
generates keys, imports Tink or touches the network: the keyset fetch is a
recorded fake, and the clock is a fake the tests advance.

``google_webhooks_public_keyset.json`` is a snapshot of Google's live keyset
(fetch date in the fixture README); it must parse through the verifier's own
parser.

Rotation contract (T-10.1-81, T-10.1-27): a known key id that fails is
``False`` (401) with no refetch; an unknown key id refetches at most once a
minute, and inside that floor, or when the refetch fails, the verifier raises
``SignatureVerificationUnavailable`` (503, Google retries).
"""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import threading
from contextlib import redirect_stdout
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import fakeredis
import pytest

from openwellness_api.event_handlers.celery_producer import ProducerSettings
from openwellness_api.google_health import build_google_health_deps, selfcheck
from openwellness_api.google_health import signature as signature_module
from openwellness_api.google_health.settings import GoogleHealthSettings
from openwellness_api.google_health.signature import (
    DEFAULT_KEYSET_URL,
    FETCH_TIMEOUT_SECONDS,
    REFETCH_FLOOR_SECONDS,
    KeysetError,
    SignatureVerificationUnavailable,
    TinkSignatureVerifier,
    parse_keyset,
)

from .google_health_harness import API_JWT_SECRET, Harness, RecordingPublisher, make_settings

FIXTURES = Path(__file__).parent / "fixtures" / "google_health_signature"
PACKAGE_DATA = (
    Path(__file__).parent.parent / "src" / "openwellness_api" / "google_health" / "data"
)
VECTORS: dict[str, Any] = json.loads((FIXTURES / "vectors.json").read_text("utf-8"))
CASES: dict[str, dict[str, Any]] = {case["name"]: case for case in VECTORS["cases"]}
KEYSET = json.dumps(VECTORS["keyset"])
KEYSET_ROTATED = json.dumps(VECTORS["keyset_rotated"])
GOOGLE_SNAPSHOT = (FIXTURES / "google_webhooks_public_keyset.json").read_text("utf-8")


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class FakeFetch:
    """Answers each fetch with the next scripted keyset text or exception."""

    script: list[str | Exception] = field(default_factory=list)
    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self) -> str:
        with self.lock:
            self.calls += 1
            item = self.script[min(self.calls, len(self.script)) - 1]
        if isinstance(item, Exception):
            raise item
        return item


def case_args(name: str) -> tuple[str, bytes]:
    case = CASES[name]
    return case["signature"], case["body"].encode("utf-8")


def make_verifier(*script: str | Exception) -> tuple[TinkSignatureVerifier, FakeFetch, FakeClock]:
    fetch = FakeFetch(list(script) or [KEYSET])
    clock = FakeClock()
    return TinkSignatureVerifier(fetch=fetch, clock=clock), fetch, clock


# --- the checked-in vectors ------------------------------------------------


def test_the_vector_file_carries_the_five_cases_and_both_keysets() -> None:
    assert {"valid", "tampered_body", "wrong_key", "not_base64", "unknown_key_id"} <= set(CASES)
    assert VECTORS["keyset"]["key"] and VECTORS["keyset_rotated"]["key"]


def test_valid_vector_verifies() -> None:
    verifier, fetch, _ = make_verifier()
    assert verifier.verify(*case_args("valid")) is True
    assert fetch.calls == 1


@pytest.mark.parametrize("name", ["tampered_body", "wrong_key", "not_base64"])
def test_invalid_vectors_are_false_without_a_refetch(name: str) -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET_ROTATED)
    assert verifier.verify(*case_args("valid")) is True
    clock.advance(REFETCH_FLOOR_SECONDS * 5)
    assert verifier.verify(*case_args(name)) is False
    assert fetch.calls == 1


@pytest.mark.parametrize(
    "signature",
    ["", "AQ==", "AF7tCgEwRQIh", "=", "AQAAAA"],
    ids=["empty", "one-byte", "non-tink-prefix", "padding-only", "short-prefix"],
)
def test_malformed_signatures_are_false(signature: str) -> None:
    verifier, _, _ = make_verifier()
    assert verifier.verify(signature, CASES["valid"]["body"].encode()) is False


def test_the_signature_covers_the_exact_raw_bytes() -> None:
    verifier, _, _ = make_verifier()
    sig, body = case_args("valid")
    reserialized = json.dumps(json.loads(body), indent=1).encode()
    assert verifier.verify(sig, body + b"\n") is False
    assert verifier.verify(sig, reserialized) is False
    assert verifier.verify(sig, body) is True


# --- rotation: unknown key id, refetch floor, 401 vs 503 -------------------


def test_unknown_key_id_refetches_once_and_accepts_the_rotated_key() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET_ROTATED)
    assert verifier.verify(*case_args("valid")) is True
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    assert verifier.verify(*case_args("unknown_key_id")) is True
    assert fetch.calls == 2
    # The rotated keyset is now cached: no further fetch for either key.
    assert verifier.verify(*case_args("unknown_key_id")) is True
    assert verifier.verify(*case_args("valid")) is True
    assert fetch.calls == 2


def test_unknown_key_id_still_absent_after_the_refetch_is_false() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET)
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    assert verifier.verify(*case_args("unknown_key_id")) is False
    assert fetch.calls == 2


def test_unknown_key_id_inside_the_floor_is_unavailable_without_a_fetch() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET_ROTATED)
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS - 1)
    with pytest.raises(SignatureVerificationUnavailable):
        verifier.verify(*case_args("unknown_key_id"))
    assert fetch.calls == 1


def test_an_unknown_key_id_judged_by_a_fetch_made_in_the_same_call_is_false() -> None:
    # The first call fetches; the keyset is as fresh as it can be, so an absent
    # key id is an invalid signature (401), exactly as after a refetch.
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET_ROTATED)
    assert verifier.verify(*case_args("unknown_key_id")) is False
    assert fetch.calls == 1
    # A second try inside the floor cannot refetch: unavailable (503).
    with pytest.raises(SignatureVerificationUnavailable):
        verifier.verify(*case_args("unknown_key_id"))
    clock.advance(REFETCH_FLOOR_SECONDS)
    assert verifier.verify(*case_args("unknown_key_id")) is True
    assert fetch.calls == 2


def test_a_failed_refetch_with_a_cached_keyset_is_unavailable_and_keeps_the_cache() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KeysetError("fetch_failed"), KEYSET_ROTATED)
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    with pytest.raises(SignatureVerificationUnavailable):
        verifier.verify(*case_args("unknown_key_id"))
    assert fetch.calls == 2
    # The cached keyset still judges known keys.
    assert verifier.verify(*case_args("valid")) is True
    assert verifier.verify(*case_args("tampered_body")) is False
    assert fetch.calls == 2


def test_an_unparseable_refetch_is_unavailable_and_keeps_the_cache() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, '{"primaryKeyId": 1, "key": "nope"}')
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    with pytest.raises(SignatureVerificationUnavailable):
        verifier.verify(*case_args("unknown_key_id"))
    assert verifier.verify(*case_args("valid")) is True


def test_a_network_error_in_the_fetch_is_unavailable() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, ConnectionError("boom"))
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    with pytest.raises(SignatureVerificationUnavailable):
        verifier.verify(*case_args("unknown_key_id"))


def test_a_fetch_failure_with_no_cached_keyset_is_unavailable_and_rate_floored() -> None:
    verifier, fetch, clock = make_verifier(KeysetError("fetch_failed"), KEYSET)
    for name in ("valid", "tampered_body", "unknown_key_id"):
        with pytest.raises(SignatureVerificationUnavailable):
            verifier.verify(*case_args(name))
    assert fetch.calls == 1
    clock.advance(REFETCH_FLOOR_SECONDS)
    assert verifier.verify(*case_args("valid")) is True
    assert fetch.calls == 2


def test_a_flood_of_unknown_key_ids_fetches_at_most_once_a_minute() -> None:
    verifier, fetch, clock = make_verifier(KEYSET)
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    outcomes: list[str] = []
    fetch_times: list[float] = []
    for _ in range(600):  # ten minutes at one request every second
        before = fetch.calls
        try:
            outcomes.append(str(verifier.verify(*case_args("unknown_key_id"))))
        except SignatureVerificationUnavailable:
            outcomes.append("unavailable")
        if fetch.calls != before:
            fetch_times.append(clock.now)
        clock.advance(1)
    assert len(fetch_times) <= 10
    assert all(b - a >= REFETCH_FLOOR_SECONDS for a, b in zip(fetch_times, fetch_times[1:]))
    assert set(outcomes) == {"False", "unavailable"}


def test_concurrent_unknown_key_ids_trigger_a_single_refetch() -> None:
    verifier, fetch, clock = make_verifier(KEYSET, KEYSET_ROTATED)
    verifier.verify(*case_args("valid"))
    clock.advance(REFETCH_FLOOR_SECONDS + 1)
    results: list[Any] = []
    start = threading.Barrier(16)

    def worker() -> None:
        start.wait()
        try:
            results.append(verifier.verify(*case_args("unknown_key_id")))
        except SignatureVerificationUnavailable:
            results.append("unavailable")

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert fetch.calls == 2
    assert results == [True] * 16


# --- the default fetch -----------------------------------------------------


@dataclass
class FakeResponse:
    status_code: int = 200
    text: str = KEYSET


def test_the_default_fetch_uses_the_keyset_url_and_a_five_second_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, Any, Any]] = []

    def fake_get(url: str, timeout: Any = None, **kwargs: Any) -> FakeResponse:
        seen.append((url, timeout, kwargs.get("allow_redirects")))
        return FakeResponse()

    monkeypatch.setattr(signature_module.requests, "get", fake_get)
    verifier = TinkSignatureVerifier("https://keys.example.test/keyset.json")
    assert verifier.verify(*case_args("valid")) is True
    # No redirect is followed: an HTTPS keyset URL cannot downgrade to HTTP.
    assert seen == [("https://keys.example.test/keyset.json", FETCH_TIMEOUT_SECONDS, False)]
    assert FETCH_TIMEOUT_SECONDS == 5


def test_a_non_200_keyset_response_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        signature_module.requests, "get", lambda url, timeout=None, **_: FakeResponse(503, "")
    )
    with pytest.raises(SignatureVerificationUnavailable):
        TinkSignatureVerifier().verify(*case_args("valid"))


def test_constructing_the_verifier_fetches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any, **__: Any) -> None:
        raise AssertionError("fetched at construction")

    monkeypatch.setattr(signature_module.requests, "get", boom)
    TinkSignatureVerifier()


# --- logs ------------------------------------------------------------------


def test_logs_carry_no_signature_body_or_key_material(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    verifier, _, clock = make_verifier(KEYSET, KeysetError("fetch_failed"), KEYSET_ROTATED)
    for name in CASES:
        clock.advance(REFETCH_FLOOR_SECONDS + 1)
        try:
            verifier.verify(*case_args(name))
        except SignatureVerificationUnavailable:
            pass
    text = caplog.text
    assert "googleHealth/signature" in text
    for case in VECTORS["cases"]:
        assert case["signature"] not in text
        assert "vector-user" not in text
    for keyset in (VECTORS["keyset"], VECTORS["keyset_rotated"]):
        for key in keyset["key"]:
            assert key["keyData"]["value"] not in text
            assert str(key["keyId"]) not in text


# --- Google's live keyset snapshot ------------------------------------------


def test_the_google_keyset_snapshot_parses_into_p256_keys() -> None:
    parsed = parse_keyset(GOOGLE_SNAPSHOT)
    snapshot = json.loads(GOOGLE_SNAPSHOT)
    assert len(parsed.keys) >= 1
    assert snapshot["primaryKeyId"] in parsed.key_ids
    assert all(key.curve == "NIST_P256" and key.hash == "SHA256" for key in parsed.keys)


def test_a_signature_under_a_key_outside_googles_snapshot_is_not_accepted() -> None:
    verifier, fetch, clock = make_verifier(GOOGLE_SNAPSHOT, GOOGLE_SNAPSHOT)
    assert verifier.verify(*case_args("valid")) is False
    clock.advance(REFETCH_FLOOR_SECONDS)
    assert verifier.verify(*case_args("valid")) is False
    assert fetch.calls == 2


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", '{"key": []}', '{"primaryKeyId": 1, "key": [{"keyId": 1}]}'],
    ids=["empty", "not-json", "array", "no-keys", "no-key-data"],
)
def test_parse_keyset_rejects_malformed_keysets(text: str) -> None:
    with pytest.raises(KeysetError):
        parse_keyset(text)


def test_the_bundled_copies_match_the_fixtures() -> None:
    bundled = (PACKAGE_DATA / "webhooks_public_keyset.json").read_text("utf-8")
    assert bundled == GOOGLE_SNAPSHOT
    vector = json.loads((PACKAGE_DATA / "selfcheck_vector.json").read_text("utf-8"))
    assert vector["keyset"] == VECTORS["keyset"]
    assert vector["body"] == CASES["valid"]["body"]
    assert vector["signature"] == CASES["valid"]["signature"]


# --- settings and deps wiring -----------------------------------------------


def test_keyset_url_defaults_to_googles_gstatic_url() -> None:
    assert GoogleHealthSettings().keyset_url == DEFAULT_KEYSET_URL
    assert DEFAULT_KEYSET_URL == (
        "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"
    )


@pytest.mark.parametrize("url", ["http://www.gstatic.com/x.json", "https://", "file:///etc/x"])
def test_a_non_https_keyset_url_is_a_settings_problem(url: str) -> None:
    problems = make_settings(keyset_url=url).problems(API_JWT_SECRET)
    assert "keyset_url_not_https" in problems
    assert url not in " ".join(problems)


def test_deps_wire_a_tink_verifier_on_the_configured_url() -> None:
    deps = build_google_health_deps(
        db=None,
        redis=fakeredis.FakeRedis(decode_responses=True),
        producer_settings=ProducerSettings(),
        settings=make_settings(keyset_url="https://keys.example.test/k.json"),
        auth_signing_secret=API_JWT_SECRET,
        publisher=RecordingPublisher(),
    )
    assert isinstance(deps.signature_verifier, TinkSignatureVerifier)
    assert deps.signature_verifier.keyset_url == "https://keys.example.test/k.json"


# --- the route with the real verifier -----------------------------------------


def _route_with_real_verifier(*script: str | Exception) -> tuple[Harness, FakeFetch, FakeClock]:
    h = Harness()
    verifier, fetch, clock = make_verifier(*script)
    h.app.state.google_health_deps = replace(h.deps, signature_verifier=verifier)
    return h, fetch, clock


def _post(h: Harness, name: str) -> Any:
    sig, body = case_args(name)
    return h.client().post(
        "/api/googleHealth/notifications",
        content=body,
        headers={
            "content-type": "application/json",
            "authorization": h.settings.webhook_secret,
            "google-health-api-signature": sig,
        },
    )


def test_route_with_the_real_verifier_publishes_a_genuine_notification() -> None:
    h, _, _ = _route_with_real_verifier()
    assert _post(h, "valid").status_code == 204
    assert h.publisher.calls == [
        ("googleHealth.handleNotification", ["vector-user", "steps", "UPSERT", ["2026-09-01"]], "scheduler_new")
    ]


@pytest.mark.parametrize("name", ["tampered_body", "wrong_key", "not_base64"])
def test_route_with_the_real_verifier_answers_401_to_bad_signatures(name: str) -> None:
    h, _, _ = _route_with_real_verifier()
    assert _post(h, name).status_code == 401
    assert h.publisher.calls == []


def test_route_answers_503_for_a_rotated_key_inside_the_floor_then_accepts_it() -> None:
    h, fetch, clock = _route_with_real_verifier(KEYSET, KEYSET_ROTATED)
    assert _post(h, "valid").status_code == 204
    assert _post(h, "unknown_key_id").status_code == 503
    clock.advance(REFETCH_FLOOR_SECONDS)
    assert _post(h, "unknown_key_id").status_code == 204
    assert fetch.calls == 2


# --- selfcheck ------------------------------------------------------------------


def _selfcheck_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    settings = make_settings()
    values = {
        "GOOGLE_HEALTH_CLIENT_ID": settings.client_id,
        "GOOGLE_HEALTH_CLIENT_SECRET": settings.client_secret,
        "GOOGLE_HEALTH_LINK_SECRET": settings.link_secret,
        "GOOGLE_HEALTH_STATE_SECRET": settings.state_secret,
        "GOOGLE_HEALTH_WEBHOOK_SECRET": settings.webhook_secret,
        "GOOGLE_HEALTH_PUBLIC_BASE_URL": settings.public_base_url,
        "API_AUTH_JWT_SECRET": API_JWT_SECRET,
        "CELERY_BROKER_URL": "redis://broker.invalid:6379/1",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _run_selfcheck(redis_client: Any) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = selfcheck.main(redis_client=redis_client)
    return code, out.getvalue()


def test_selfcheck_passes_every_check_with_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _selfcheck_env(monkeypatch)
    code, out = _run_selfcheck(fakeredis.FakeRedis(decode_responses=True))
    assert out.splitlines() == [
        "PASS settings",
        "PASS signature_vector",
        "PASS keyset_snapshot",
        "PASS token_roundtrip",
        "PASS redis_ping",
        "PASS publisher_config",
    ]
    assert code == 0


def test_selfcheck_fails_on_an_invalid_setting_and_prints_no_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _selfcheck_env(monkeypatch, GOOGLE_HEALTH_WEBHOOK_SECRET="short-webhook-value", CELERY_BROKER_URL="")
    code, out = _run_selfcheck(fakeredis.FakeRedis(decode_responses=True))
    assert code == 1
    assert "FAIL settings: webhook_secret_short" in out.splitlines()
    assert "FAIL publisher_config" in out
    for value in ("short-webhook-value", make_settings().link_secret, API_JWT_SECRET):
        assert value not in out


def test_selfcheck_fails_when_redis_does_not_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class DeadRedis:
        def __getattr__(self, name: str) -> Any:
            def fail(*_: Any, **__: Any) -> Any:
                raise ConnectionError("redis down at redis://secret-host")

            return fail

    _selfcheck_env(monkeypatch)
    code, out = _run_selfcheck(DeadRedis())
    assert code == 1
    assert "FAIL redis_ping" in out
    assert "FAIL token_roundtrip" in out
    assert "secret-host" not in out


def test_selfcheck_runs_as_a_module_and_reports_unset_settings_by_name() -> None:
    env = {"PATH": "/usr/bin:/bin", "REDIS_URL": "redis://127.0.0.1:1/0"}
    result = subprocess.run(
        [sys.executable, "-m", "openwellness_api.google_health.selfcheck"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    assert lines[0].startswith("FAIL settings: ")
    assert "GOOGLE_HEALTH_WEBHOOK_SECRET" in lines[0]
    assert "PASS signature_vector" in lines
    assert "PASS keyset_snapshot" in lines
    assert [line.split()[1].rstrip(":") for line in lines] == [
        "settings",
        "signature_vector",
        "keyset_snapshot",
        "token_roundtrip",
        "redis_ping",
        "publisher_config",
    ]
