from __future__ import annotations

import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from models.trip_brief import TripBrief, TripStatus


INTAKE_PROMPT = """You extract Vietnam team trip planning fields from the user message.
Return ONLY valid JSON with these keys (use null for unknown):
{
  "origin_city": string|null,
  "destination_city": string|null,
  "start_date": "YYYY-MM-DD"|null,
  "end_date": "YYYY-MM-DD"|null,
  "headcount": number|null,
  "budget_vnd": number|null,
  "budget_mode": "per_person"|"total"|null,
  "preferences": string[],
  "constraints": string[]
}
Use Vietnamese city names in English (e.g. "Da Nang", "Ho Chi Minh City", "Hanoi").
If budget is given per person, set budget_mode to "per_person".
Parse dates like "Mar 20-23" using the current year if year omitted."""


def _parse_vnd(text: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(m|mil|million|k|000)?", text.lower())
    if not match:
        return None
    value = float(match.group(1))
    suffix = match.group(2) or ""
    if "m" in suffix or "mil" in suffix or "million" in suffix:
        return int(value * 1_000_000)
    if suffix == "k":
        return int(value * 1_000)
    if value < 1000:
        return int(value * 1_000_000)
    return int(value)


def _rule_extract(message: str) -> dict:
    """Fast path for demo-style messages without LLM."""
    lower = message.lower()
    data: dict = {"preferences": [], "constraints": []}

    cities = {
        "da nang": "Da Nang",
        "danang": "Da Nang",
        "hanoi": "Hanoi",
        "ho chi minh": "Ho Chi Minh City",
        "hcmc": "Ho Chi Minh City",
        "saigon": "Ho Chi Minh City",
        "nha trang": "Nha Trang",
        "phu quoc": "Phu Quoc",
        "hue": "Hue",
        "hoi an": "Hoi An",
    }
    found = [(key, name) for key, name in cities.items() if key in lower]
    found_names = [name for _, name in found]

    if " from " in f" {lower} " and found:
        parts = re.split(r"\bfrom\b", lower, maxsplit=1)
        dest_part, origin_part = parts[0], parts[1] if len(parts) > 1 else ""
        for key, name in cities.items():
            if key in origin_part:
                data["origin_city"] = name
            if key in dest_part:
                data["destination_city"] = name
    elif len(found_names) >= 2:
        data["origin_city"] = found_names[0]
        data["destination_city"] = found_names[1]
    elif len(found_names) == 1:
        data["destination_city"] = found_names[0]

    headcount = re.search(r"(\d+)\s*(people|person|members|pax)", lower)
    if headcount:
        data["headcount"] = int(headcount.group(1))

    budget = re.search(r"(\d+(?:\.\d+)?)\s*(m|mil|million)\s*vnd?", lower)
    if budget:
        data["budget_vnd"] = int(float(budget.group(1)) * 1_000_000)
        data["budget_mode"] = "per_person" if "per person" in lower or "/person" in lower else "per_person"
    elif "vnd" in lower or "budget" in lower:
        parsed = _parse_vnd(lower)
        if parsed:
            data["budget_vnd"] = parsed
            data["budget_mode"] = "per_person"

    for pref in ("beach", "food", "hiking", "culture", "nightlife", "nature"):
        if pref in lower:
            data["preferences"].append(pref)

    date_match = re.search(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
        lower,
    )
    if date_match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months[date_match.group(1)[:3]]
        year = date.today().year
        start_day = int(date_match.group(2))
        end_day = int(date_match.group(3))
        data["start_date"] = date(year, month, start_day)
        data["end_date"] = date(year, month, end_day)

    return data


def merge_brief(existing: TripBrief, extracted: dict) -> TripBrief:
    updates = {k: v for k, v in extracted.items() if v is not None and v != []}
    merged = existing.model_copy(update=updates)
    merged.refresh_missing_fields()
    return merged


def intake_node(state: dict, llm) -> dict:
    message = state.get("user_message", "")
    existing = TripBrief(**state.get("trip_brief", {}))
    if state.get("team_id"):
        existing.team_id = state["team_id"]

    rule_data = _rule_extract(message)
    brief = merge_brief(existing, rule_data)

    if brief.missing_fields:
        try:
            response = llm.invoke(
                [
                    SystemMessage(content=INTAKE_PROMPT),
                    HumanMessage(content=message),
                ]
            )
            content = response.content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            llm_data = json.loads(content)
            for key in ("start_date", "end_date"):
                if llm_data.get(key):
                    llm_data[key] = date.fromisoformat(llm_data[key])
            brief = merge_brief(brief, llm_data)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    brief.refresh_missing_fields()

    if brief.missing_fields:
        field = brief.missing_fields[0]
        prompts = {
            "origin_city": "Where is your team traveling from? (e.g. Ho Chi Minh City)",
            "destination_city": "Which city in Vietnam would you like to visit?",
            "start_date": "What is the trip start date? (YYYY-MM-DD)",
            "end_date": "What is the trip end date? (YYYY-MM-DD)",
            "budget_vnd": "What is your budget per person in VND? (e.g. 5000000)",
            "headcount": "How many people are traveling?",
        }
        question = prompts.get(field, f"Please provide: {field}")
        return {
            "trip_brief": brief.model_dump(mode="json"),
            "phase": "intake",
            "response": question,
        }

    brief.status = TripStatus.SEARCHING
    return {
        "trip_brief": brief.model_dump(mode="json"),
        "phase": "searching",
    }
