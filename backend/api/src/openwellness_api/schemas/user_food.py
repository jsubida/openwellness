"""UserFood resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class UserFood(ResourceBase):
    """UserFood resource."""

    food_id: str
    name: str
    amount: float
    source_type: int
    eaten_at: float
    fat: float | None = 0.0
    calories: float | None = 0.0
    serving_name: str | None = None
    serving_id: str | None = None
    cholesterol: float | None = 0.0
    fiber: float | None = 0.0
    protein: float | None = 0.0
    sat_fat: float | None = 0.0
    sodium: float | None = 0.0
    sugars: float | None = 0.0
    total_carbohydrate: float | None = 0.0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class UserFoodCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/userFoods``."""

    model_config = SCHEMA_CONFIG

    food_id: str
    name: str
    amount: float
    source_type: int
    eaten_at: float
    fat: float | None = 0.0
    calories: float | None = 0.0
    serving_name: str | None = None
    serving_id: str | None = None
    cholesterol: float | None = 0.0
    fiber: float | None = 0.0
    protein: float | None = 0.0
    sat_fat: float | None = 0.0
    sodium: float | None = 0.0
    sugars: float | None = 0.0
    total_carbohydrate: float | None = 0.0
    study_id: str = ""


class UserFoodUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/userFoods/{id}``."""

    model_config = SCHEMA_CONFIG

    food_id: str | None = None
    name: str | None = None
    amount: float | None = None
    source_type: int | None = None
    eaten_at: float | None = None
    fat: float | None = None
    calories: float | None = None
    serving_name: str | None = None
    serving_id: str | None = None
    cholesterol: float | None = None
    fiber: float | None = None
    protein: float | None = None
    sat_fat: float | None = None
    sodium: float | None = None
    sugars: float | None = None
    total_carbohydrate: float | None = None
    study_id: str | None = None


UserFoodList = list_response_model("userFoods", UserFood)
