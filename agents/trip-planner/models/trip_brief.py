from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TripStatus(str, Enum):
    INTAKE = "intake"
    SEARCHING = "searching"
    PLANNING = "planning"
    DONE = "done"


class TripBrief(BaseModel):
    team_id: str = "default-team"
    headcount: int = Field(default=10, ge=1, le=100)
    origin_city: str | None = None
    destination_city: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    nights: int | None = None
    budget_mode: Literal["per_person", "total"] = "per_person"
    budget_vnd: int | None = None
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    status: TripStatus = TripStatus.INTAKE
    missing_fields: list[str] = Field(default_factory=list)

    def compute_nights(self) -> int | None:
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days
            return max(delta, 1)
        return self.nights

    def refresh_missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.origin_city:
            missing.append("origin_city")
        if not self.destination_city:
            missing.append("destination_city")
        if not self.start_date:
            missing.append("start_date")
        if not self.end_date:
            missing.append("end_date")
        if self.budget_vnd is None:
            missing.append("budget_vnd")
        if self.headcount < 1:
            missing.append("headcount")
        self.missing_fields = missing
        self.nights = self.compute_nights()
        if missing:
            self.status = TripStatus.INTAKE
        return missing

    @field_validator("preferences", "constraints", mode="before")
    @classmethod
    def _coerce_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value else []
        return list(value)
