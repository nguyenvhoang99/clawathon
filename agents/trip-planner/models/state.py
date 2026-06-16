from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from models.budget import BudgetLedger
from models.trip_brief import TripBrief


class TripState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_message: str
    team_id: str
    session_id: str | None
    trip_brief: dict[str, Any]
    stay_results: dict[str, Any]
    transport_results: dict[str, Any]
    activity_results: dict[str, Any]
    weather_results: dict[str, Any]
    budget_ledger: dict[str, Any]
    itinerary: dict[str, Any]
    plan: dict[str, Any]
    response: str
    data_sources: list[str]
    phase: str
    intake_field: str
    location_prompt: bool
