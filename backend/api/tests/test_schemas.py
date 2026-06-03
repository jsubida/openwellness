"""Response-schema contracts against real-data shapes."""

from openwellness_api.schemas.study import Study


def test_study_allows_null_end_intervention_week() -> None:
    """Real study docs carry `end_intervention_week: null`; the response
    model must accept it rather than 400 on serialization.
    """
    s = Study.model_validate(
        {"name": "studies/x", "app_id": "a", "end_intervention_week": None}
    )
    assert s.end_intervention_week is None


def test_study_defaults_end_intervention_week_when_absent() -> None:
    s = Study.model_validate({"name": "studies/x", "app_id": "a"})
    assert s.end_intervention_week == 99999
