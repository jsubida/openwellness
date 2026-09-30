"""Google Health settings validation (10.1-05 Task 2, T-10.1-75).

``GoogleHealthSettings.problems`` returns rule names only. When any rule
fails, ``build_google_health_deps`` logs one WARNING listing the names and
every Google Health route answers 503 with the generic page; neither the
WARNING nor the page carries a setting value.
"""

from __future__ import annotations

import logging

import pytest

from .google_health_harness import (
    API_JWT_SECRET,
    AUTHORIZE_PATH,
    FINISH_PATH,
    LINKS_PATH,
    Harness,
    make_settings,
)

OK_HOLD = "5f0000000000000000000a01, 5f0000000000000000000A02"


def test_valid_settings_have_no_problems() -> None:
    assert make_settings().problems(API_JWT_SECRET) == []
    assert make_settings(migration_hold="*").problems(API_JWT_SECRET) == []
    assert make_settings(migration_hold=OK_HOLD).problems(API_JWT_SECRET) == []
    assert make_settings(public_base_url="https://example.test/").problems(API_JWT_SECRET) == []


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"link_secret": "short-link-secret"}, "link_secret_short"),
        ({"state_secret": "short-state-secret"}, "state_secret_short"),
        ({"webhook_secret": "short-webhook-secret"}, "webhook_secret_short"),
        (
            {
                "link_secret": "shared-secret-value-that-is-long-enough-1",
                "state_secret": "shared-secret-value-that-is-long-enough-1",
            },
            "secrets_not_distinct",
        ),
        ({"state_secret": API_JWT_SECRET}, "secret_reuses_api_jwt"),
        ({"public_base_url": "http://example.test"}, "public_base_url_not_https_origin"),
        ({"public_base_url": "https://example.test/api"}, "public_base_url_not_https_origin"),
        ({"public_base_url": "https://example.test?x=1"}, "public_base_url_not_https_origin"),
        ({"public_base_url": "https://example.test#frag"}, "public_base_url_not_https_origin"),
        ({"public_base_url": "https://"}, "public_base_url_not_https_origin"),
        ({"public_base_url": "https://user:pw@example.test"}, "public_base_url_not_https_origin"),
        ({"client_id": "not-a-google-client"}, "client_id_format"),
        ({"client_id": ".apps.googleusercontent.com"}, "client_id_format"),
        ({"migration_hold": "not-a-study"}, "migration_hold_malformed"),
        ({"migration_hold": "*,5f0000000000000000000a01"}, "migration_hold_malformed"),
        ({"migration_hold": "5f0000000000000000000a01,,"}, "migration_hold_malformed"),
    ],
)
def test_each_rule_is_reported_by_name(overrides: dict[str, str], rule: str) -> None:
    problems = make_settings(**overrides).problems(API_JWT_SECRET)
    assert rule in problems
    for value in overrides.values():
        if value:
            assert value not in " ".join(problems)


def test_held_study_ids_parse() -> None:
    assert make_settings(migration_hold="").held_study_ids() == frozenset()
    assert make_settings(migration_hold=" * ").held_study_ids() == "*"
    assert make_settings(migration_hold=OK_HOLD).held_study_ids() == frozenset(
        {"5f0000000000000000000a01", "5f0000000000000000000a02"}
    )
    # A malformed hold fails closed: every study is held until it is fixed.
    assert make_settings(migration_hold="oops").held_study_ids() == "*"


def test_settings_repr_never_carries_a_secret() -> None:
    settings = make_settings()
    text = repr(settings) + str(settings)
    for secret in (
        settings.client_secret,
        settings.link_secret,
        settings.state_secret,
        settings.webhook_secret,
    ):
        assert secret not in text


def _all_routes(h: Harness) -> list[int]:
    client = h.client()
    pid = h.seed_participant()
    return [
        client.post(LINKS_PATH, json={"participantId": pid}).status_code,
        client.get(AUTHORIZE_PATH, params={"t": "x"}).status_code,
        client.get(FINISH_PATH, params={"code": "c", "state": "s"}).status_code,
    ]


def test_an_invalid_setting_disables_every_route_with_one_value_free_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    weak = "weak-link-secret-sentinel"
    with caplog.at_level(logging.DEBUG):
        h = Harness(settings=make_settings(link_secret=weak, public_base_url="http://x.test"))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "link_secret_short" in message
    assert "public_base_url_not_https_origin" in message
    assert weak not in caplog.text
    assert "x.test" not in caplog.text

    assert _all_routes(h) == [503, 503, 503]
    client = h.client()
    page = client.get(FINISH_PATH, params={"code": "c", "state": "s"}).text
    assert weak not in page
    assert h.google.exchanges == []


def test_reusing_the_api_signing_secret_disables_the_routes() -> None:
    h = Harness(settings=make_settings(link_secret=API_JWT_SECRET))
    assert h.deps.disabled
    assert _all_routes(h) == [503, 503, 503]


def test_unset_keys_disable_the_routes_and_name_the_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        h = Harness(settings=make_settings(client_secret="", webhook_secret=""))
    (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert "GOOGLE_HEALTH_CLIENT_SECRET" in warning.getMessage()
    assert "GOOGLE_HEALTH_WEBHOOK_SECRET" in warning.getMessage()
    assert _all_routes(h) == [503, 503, 503]
