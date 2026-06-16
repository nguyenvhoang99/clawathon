from __future__ import annotations

from graph.nodes.budget import build_budget_ledger
from models.trip_brief import TripBrief, TripStatus


def budget_node(state: dict) -> dict:
    brief = TripBrief(**state["trip_brief"])
    ledger = build_budget_ledger(
        brief,
        state.get("stay_results", {}),
        state.get("transport_results", {}),
        state.get("activity_results", {}),
    )
    brief.status = TripStatus.PLANNING
    return {
        "budget_ledger": ledger.model_dump(),
        "trip_brief": brief.model_dump(mode="json"),
        "phase": "planning",
    }
