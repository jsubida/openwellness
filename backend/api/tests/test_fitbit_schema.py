"""The ``/v1/fitbits`` wire shape never carries an OAuth token."""

from __future__ import annotations

from openwellness_core.domain.models.fitbit import Fitbit as FitbitEntity

from openwellness_api.common.handlers import serialize_many, serialize_one
from openwellness_api.schemas.fitbit import Fitbit, FitbitCreate, FitbitUpdate

ACCESS = "ACCESS-TOKEN-SENTINEL"
REFRESH = "REFRESH-TOKEN-SENTINEL"


def _entity() -> FitbitEntity:
    return FitbitEntity(
        participant_id="5f0000000000000000000a01",
        access_token=ACCESS,
        refresh_token=REFRESH,
        owner_id="OWNER1",
    )


def test_a_fitbit_response_never_carries_its_tokens() -> None:
    one = serialize_one(_entity(), Fitbit, collection="fitbits")
    many = serialize_many([_entity()], Fitbit, collection="fitbits")
    for body in (one, *many):
        assert body["ownerId"] == "OWNER1"
        assert "accessToken" not in body and "refreshToken" not in body
        assert ACCESS not in str(body) and REFRESH not in str(body)


def test_the_tokens_are_still_accepted_on_write() -> None:
    body = {"participantId": "p", "accessToken": ACCESS, "refreshToken": REFRESH}
    assert FitbitCreate.model_validate(body).access_token == ACCESS
    assert FitbitUpdate.model_validate(body).refresh_token == REFRESH
    assert "accessToken" not in Fitbit.model_json_schema(by_alias=True)["properties"]
