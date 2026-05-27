"""Goal resource schemas — discriminated union over ``kind``."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Goal(ResourceBase):
    """Goal resource (response shape covers all subtypes by-field)."""

    kind: int = 0
    start_date: float = 0.0
    owner: str = ""
    study_id: str = ""
    updated_by: str = ""
    # LegacyGoal-only fields, optional on the response so all kinds round-trip.
    activity: float | None = None
    calories: float | None = None
    fat: float | None = None
    steps: int | None = None
    weight: float | None = None


class _GoalCreateBase(BaseModel):
    """Common subset of Goal create bodies."""

    model_config = SCHEMA_CONFIG

    start_date: float = 0.0
    study_id: str = ""


class WeeklyGoalCreate(_GoalCreateBase):
    kind: Literal[0] = 0


class DailyGoalCreate(_GoalCreateBase):
    kind: Literal[1] = 1


class LegacyGoalCreate(_GoalCreateBase):
    """Legacy Goal carrying nutrition targets.

    The wire-only ``kind: 2`` discriminator is stripped before constructing
    the core ``LegacyGoal`` (which has no ``kind`` field).
    """

    kind: Literal[2] = 2
    activity: float = 0.0
    calories: float = 0.0
    fat: float = 0.0
    steps: int = 0
    weight: float = 0.0


GoalCreate = Annotated[
    Union[WeeklyGoalCreate, DailyGoalCreate, LegacyGoalCreate],
    Field(discriminator="kind"),
]


class GoalUpdate(BaseModel):
    """Patch only common / nutrition-target fields. Kind transitions
    aren't supported."""

    model_config = SCHEMA_CONFIG

    start_date: float | None = None
    activity: float | None = None
    calories: float | None = None
    fat: float | None = None
    steps: int | None = None
    weight: float | None = None


GoalList = list_response_model("goals", Goal)
