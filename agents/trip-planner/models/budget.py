from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DataSource = Literal["api", "osm", "estimate", "mock"]


class CategoryBudget(BaseModel):
    low: int
    mid: int
    high: int
    notes: str = ""
    source: DataSource = "estimate"
    room_count: int | None = None


class BudgetLedger(BaseModel):
    currency: str = "VND"
    headcount: int
    categories: dict[str, CategoryBudget] = Field(default_factory=dict)
    contingency_pct: int = 10
    total_per_person: dict[str, int] = Field(default_factory=dict)
    total_group: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    over_budget: bool = False
    tradeoff_options: list[str] = Field(default_factory=list)
