"""AIP-160 ``filter=`` parser unit tests."""

import pytest
from fastapi import HTTPException

from openwellness_api.common.filter import parse_filter


def test_empty_filter_returns_empty_dict() -> None:
    assert parse_filter(None, allowed_fields={"kind": int}) == {}
    assert parse_filter("", allowed_fields={"kind": int}) == {}


def test_single_clause_coerced_by_type() -> None:
    assert parse_filter("kind=1", allowed_fields={"kind": int}) == {"kind": 1}


def test_multiple_clauses_joined_by_and() -> None:
    out = parse_filter(
        "kind=1 AND week=5", allowed_fields={"kind": int, "week": int}
    )
    assert out == {"kind": 1, "week": 5}


def test_quoted_string_value_unwrapped() -> None:
    out = parse_filter('subtype="alpha"', allowed_fields={"subtype": str})
    assert out == {"subtype": "alpha"}


def test_unknown_field_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_filter("nope=1", allowed_fields={"kind": int})
    assert exc.value.status_code == 400


def test_unsupported_operator_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_filter("kind>1", allowed_fields={"kind": int})
    assert exc.value.status_code == 400


def test_or_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_filter("kind=1 or kind=2", allowed_fields={"kind": int})
    assert exc.value.status_code == 400


def test_malformed_clause_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_filter("kind", allowed_fields={"kind": int})
    assert exc.value.status_code == 400


def test_bad_value_type_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        parse_filter("kind=notanint", allowed_fields={"kind": int})
    assert exc.value.status_code == 400
