"""Build the final plan structure (overall + spending + activities) for the web.

The deterministic skeleton (days, budget aggregation, Zalopay categories)
is computed in Python; the LLM only fills in the narrative summary and
picks the main team-building activity day from the curated pool.
"""

from __future__ import annotations

from datetime import date, timedelta

from models.trip_brief import TripBrief

from .young_activities import curate_activity_pool
from .zalopay_pricing import build_spending


def _format_date_range(start: date | None, end: date | None) -> str:
    if not start or not end:
        return ""
    if start == end:
        return start.strftime("%d/%m/%Y")
    if start.year == end.year and start.month == end.month:
        return f"{start.day:02d}–{end.day:02d}/{end.month:02d}/{end.year}"
    return f"{start.strftime('%d/%m/%Y')} → {end.strftime('%d/%m/%Y')}"


def _date_iter(start: date | None, nights: int) -> list[str]:
    if not start:
        return []
    return [(start + timedelta(days=i)).isoformat() for i in range(max(nights, 1))]


def _budget_range(budget_ledger: dict | None, headcount: int) -> dict:
    if not budget_ledger:
        return {"low": 0, "mid": 0, "high": 0, "perPerson": True, "currency": "VND"}
    per_person = budget_ledger.get("total_per_person") or {}
    return {
        "low": int(per_person.get("low", 0)),
        "mid": int(per_person.get("mid", 0)),
        "high": int(per_person.get("high", 0)),
        "perPerson": True,
        "currency": budget_ledger.get("currency", "VND"),
        "groupLow": int(per_person.get("low", 0)) * headcount,
        "groupHigh": int(per_person.get("high", 0)) * headcount,
    }


def _assign_activities_to_days(
    activity_pool: list[dict],
    weather_days: list[dict],
    nights: int,
    dates: list[str],
) -> list[dict]:
    """Distribute curated activities across days (2 per day), respecting weather."""
    if not activity_pool:
        return [
            {
                "day": i + 1,
                "date": dates[i] if i < len(dates) else None,
                "activities": [],
                "note": "Chưa có dữ liệu hoạt động",
            }
            for i in range(max(nights, 1))
        ]

    outdoor = [a for a in activity_pool if not a.get("indoor")]
    indoor = [a for a in activity_pool if a.get("indoor")]
    used: set[str] = set()
    cursor = 0
    days: list[dict] = []
    for i in range(max(nights, 1)):
        wx = weather_days[i] if i < len(weather_days) else {}
        rain = wx.get("rain_likely")
        primary_pool = (indoor if rain else outdoor) or activity_pool
        picks: list[dict] = []
        attempts = 0
        while len(picks) < 2 and attempts < len(primary_pool) * 2:
            candidate = primary_pool[cursor % len(primary_pool)]
            cursor += 1
            attempts += 1
            key = candidate.get("name")
            if key in used:
                continue
            used.add(key)
            picks.append(candidate)
        if len(picks) < 2:
            for candidate in activity_pool:
                if candidate.get("name") in used:
                    continue
                used.add(candidate.get("name"))
                picks.append(candidate)
                if len(picks) >= 2:
                    break
        days.append(
            {
                "day": i + 1,
                "date": dates[i] if i < len(dates) else wx.get("date"),
                "weather": wx.get("condition"),
                "outdoorOk": wx.get("outdoor_ok", True) and not rain,
                "note": "Trời mưa — ưu tiên hoạt động trong nhà" if rain else "Thích hợp hoạt động ngoài trời",
                "activities": [
                    {
                        "name": p.get("name"),
                        "category": p.get("category"),
                        "tags": p.get("tags") or [],
                        "source": p.get("source") or "curated",
                    }
                    for p in picks
                ],
            }
        )
    return days


def _pick_main_team_building_day(days: list[dict]) -> dict | None:
    """Choose the day with the most "team building" tagged activity, preferring a sunny middle day."""
    if not days:
        return None

    total = len(days)
    middle = (total + 1) / 2

    def score(day: dict) -> tuple[int, float, int]:
        bonus = 0
        for act in day.get("activities") or []:
            tags = [t.lower() for t in (act.get("tags") or [])]
            if any("team" in t or "adventure" in t for t in tags):
                bonus += 3
            if act.get("category") in {"beach", "nature"}:
                bonus += 1
        if day.get("outdoorOk"):
            bonus += 1
        day_no = day.get("day", 1)
        edge_penalty = 0 if 1 < day_no < total else 1
        return (-bonus, edge_penalty, int(abs(day_no - middle) * 10))

    chosen = sorted(days, key=score)[0]
    activities = chosen.get("activities") or []
    return {
        "day": chosen.get("day"),
        "date": chosen.get("date"),
        "activity": activities[0]["name"] if activities else None,
        "reason": "Thời tiết thuận lợi, hoạt động phù hợp với team building",
    }


def build_plan(state: dict) -> dict:
    """Build the structured plan (overall + spending + activities) for the web."""
    brief = TripBrief(**state["trip_brief"])
    headcount = brief.headcount
    nights = brief.nights or 1
    dates = _date_iter(brief.start_date, nights)

    weather_days = (state.get("weather_results") or {}).get("days") or []
    activity_pool = curate_activity_pool(
        brief.destination_city,
        state.get("activity_results"),
        brief.preferences,
    )

    day_plan = _assign_activities_to_days(activity_pool, weather_days, nights, dates)
    main_day = _pick_main_team_building_day(day_plan)
    spending = build_spending(state.get("trip_brief") or {})

    budget_range = _budget_range(state.get("budget_ledger"), headcount)

    overall = {
        "destination": brief.destination_city,
        "origin": brief.origin_city,
        "headcount": headcount,
        "nights": nights,
        "startDate": brief.start_date.isoformat() if brief.start_date else None,
        "endDate": brief.end_date.isoformat() if brief.end_date else None,
        "dateRangeLabel": _format_date_range(brief.start_date, brief.end_date),
        "mainTeamBuildingDay": main_day,
        "budgetRange": budget_range,
    }

    activities_section = {
        "city": (state.get("activity_results") or {}).get("city") or brief.destination_city,
        "pool": [
            {
                "name": a.get("name"),
                "category": a.get("category"),
                "tags": a.get("tags") or [],
                "source": a.get("source"),
            }
            for a in activity_pool[:12]
        ],
        "days": day_plan,
    }

    return {
        "overall": overall,
        "spending": spending,
        "activities": activities_section,
    }
