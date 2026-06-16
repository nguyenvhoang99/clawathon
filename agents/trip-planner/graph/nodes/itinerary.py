from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from models.trip_brief import TripBrief, TripStatus


ITINERARY_PROMPT = """You are a Vietnam team trip planner. Create a day-by-day itinerary using ONLY the provided JSON data.
Rules:
- Cite real place names from activities and stays lists only — do not invent venues
- Schedule outdoor/beach activities on days where outdoor_ok is true
- Move outdoor plans to indoor alternatives on rain_likely days (museums, food, markets)
- Include transport recommendation and budget summary (low/mid/high per person)
- Mention team size and room count
- If over_budget is true, include tradeoff_options
- Format with clear headings: Overview, Day 1..., Transport, Budget, Weather alerts
- Keep under 800 words"""


def itinerary_node(state: dict, llm) -> dict:
    brief = TripBrief(**state["trip_brief"])
    context = {
        "trip_brief": state.get("trip_brief"),
        "stay_results": state.get("stay_results"),
        "transport_results": state.get("transport_results"),
        "activity_results": state.get("activity_results"),
        "weather_results": state.get("weather_results"),
        "budget_ledger": state.get("budget_ledger"),
    }

    response = llm.invoke(
        [
            SystemMessage(content=ITINERARY_PROMPT),
            HumanMessage(content=json.dumps(context, ensure_ascii=False, default=str)),
        ]
    )

    days = _build_day_plan(state)
    brief.status = TripStatus.DONE

    return {
        "response": response.content,
        "itinerary": {"days": days},
        "trip_brief": brief.model_dump(mode="json"),
        "phase": "done",
    }


def _build_day_plan(state: dict) -> list[dict]:
    brief = TripBrief(**state["trip_brief"])
    weather_days = state.get("weather_results", {}).get("days", [])
    activities = state.get("activity_results", {}).get("activities", [])
    outdoor = [a for a in activities if not a.get("indoor")]
    indoor = [a for a in activities if a.get("indoor")]

    plan = []
    nights = brief.nights or len(weather_days) or 1
    for i in range(nights):
        wx = weather_days[i] if i < len(weather_days) else {}
        if wx.get("rain_likely"):
            picks = indoor[:2] if indoor else activities[:2]
            note = "Rain likely — indoor focus"
        else:
            picks = outdoor[:2] if outdoor else activities[:2]
            note = "Good for outdoor activities"
        plan.append(
            {
                "day": i + 1,
                "date": wx.get("date"),
                "weather": wx.get("condition"),
                "outdoor_ok": wx.get("outdoor_ok", True),
                "activities": [p.get("name") for p in picks],
                "note": note,
            }
        )
    return plan
