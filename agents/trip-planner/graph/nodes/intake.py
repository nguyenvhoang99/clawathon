from __future__ import annotations

import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from graph.nodes.date_utils import (
    coerce_dates_to_current_year_if_omitted,
    parse_dates_from_text,
    resolve_year_month,
    year_explicit_in_text,
)
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
Today's reference date is {today}. If month is omitted when parsing dates, use the current month.
If year is omitted, use the current year ({year}). Never default to 2024 or other past years.
Parse Vietnamese dates like "20-23/3", "20-23/6/2026", or "20/3" accordingly."""


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
        "đà nẵng": "Da Nang",
        "hanoi": "Hanoi",
        "ha noi": "Hanoi",
        "hà nội": "Hanoi",
        "ho chi minh": "Ho Chi Minh City",
        "hcmc": "Ho Chi Minh City",
        "saigon": "Ho Chi Minh City",
        "tp.hcm": "Ho Chi Minh City",
        "tp hcm": "Ho Chi Minh City",
        "nha trang": "Nha Trang",
        "phu quoc": "Phu Quoc",
        "phú quốc": "Phu Quoc",
        "hue": "Hue",
        "huế": "Hue",
        "hoi an": "Hoi An",
        "hội an": "Hoi An",
    }
    found = [(key, name) for key, name in cities.items() if key in lower]
    found_names = [name for _, name in found]

    origin_markers = re.search(r"\b(từ|from)\b", lower)
    if origin_markers:
        parts = re.split(r"\b(?:từ|from)\b", lower, maxsplit=1)
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

    data.update(parse_dates_from_text(message))

    return data


def _user_denied_location(message: str) -> bool:
    lower = message.lower()
    patterns = (
        r"t[uừ]\s*ch[oố]i",
        r"kh[oô]ng\s*(cho\s*ph[eé]p|đ[ồo]ng\s*[ýy]|chia\s*s[eẻ]|d[uù]ng\s*v[iị]\s*tr[ií])",
        r"location\s*denied",
        r"deny\s*location",
        r"kh[oô]ng\s*,?\s*t[oô]i\s*s[eẽ]\s*nh[aậ]p",
        r"nh[aậ]p\s*th[uủ]\s*c[oô]ng",
    )
    return any(re.search(p, lower) for p in patterns)


def merge_brief(existing: TripBrief, extracted: dict) -> TripBrief:
    updates = {k: v for k, v in extracted.items() if v is not None and v != []}
    merged = existing.model_copy(update=updates)
    merged.refresh_missing_fields()
    return merged


def _normalize_brief_dates(message: str, brief: TripBrief) -> TripBrief:
    start, end = coerce_dates_to_current_year_if_omitted(message, brief.start_date, brief.end_date)
    if start != brief.start_date or end != brief.end_date:
        brief = brief.model_copy(update={"start_date": start, "end_date": end})
        brief.refresh_missing_fields()
    return brief


def intake_node(state: dict, llm) -> dict:
    message = state.get("user_message", "")
    existing = TripBrief(**state.get("trip_brief", {}))
    if state.get("team_id"):
        existing.team_id = state["team_id"]

    rule_data = _rule_extract(message)
    brief = merge_brief(existing, rule_data)

    if brief.missing_fields:
        try:
            today = date.today()
            prompt = (
                INTAKE_PROMPT.replace("{today}", today.isoformat()).replace("{year}", str(today.year))
            )
            response = llm.invoke(
                [
                    SystemMessage(content=prompt),
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
                    parsed = date.fromisoformat(llm_data[key])
                    if year_explicit_in_text(message):
                        year, month = resolve_year_month(parsed.year, parsed.month)
                        llm_data[key] = date(year, month, parsed.day)
                    else:
                        year, month = resolve_year_month(None, parsed.month)
                        llm_data[key] = date(year, month, parsed.day)
            brief = merge_brief(brief, llm_data)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    brief = _normalize_brief_dates(message, brief)
    brief.refresh_missing_fields()

    if brief.missing_fields:
        field = brief.missing_fields[0]
        location_prompt = False
        if field == "origin_city":
            if _user_denied_location(message):
                question = (
                    "Bạn chưa cung cấp điểm khởi hành. Không có thông tin này, mình không thể ước tính "
                    "vé máy bay/tàu/xe và chi phí di chuyển chính xác. "
                    "Vui lòng nhập thành phố hoặc tỉnh xuất phát trong ô nhập (vd: TP.HCM, Hà Nội, Đà Nẵng)."
                )
            else:
                question = (
                    "Mình chưa biết team bạn khởi hành từ đâu. Bạn có thể cho phép truy cập vị trí "
                    "để mình tự điền thành phố/tỉnh xuất phát, hoặc gõ trực tiếp trong ô nhập "
                    "(vd: TP.HCM, Hà Nội). Chọn «Cho phép vị trí» bên dưới hoặc nhập thủ công."
                )
                location_prompt = True
        else:
            prompts = {
                "destination_city": "Bạn muốn đi thành phố nào ở Việt Nam? (vd: Đà Nẵng, Nha Trang)",
                "start_date": "Ngày bắt đầu chuyến đi là khi nào? (vd: 20/3/2026)",
                "end_date": "Ngày kết thúc chuyến đi là khi nào? (vd: 23/3/2026)",
                "budget_vnd": "Ngân sách dự kiến mỗi người là bao nhiêu VND? (vd: 5000000)",
                "headcount": "Có bao nhiêu người tham gia chuyến đi?",
            }
            question = prompts.get(field, f"Vui lòng cung cấp: {field}")
        return {
            "trip_brief": brief.model_dump(mode="json"),
            "phase": "intake",
            "response": question,
            "intake_field": field,
            "location_prompt": location_prompt,
        }

    brief.status = TripStatus.SEARCHING
    return {
        "trip_brief": brief.model_dump(mode="json"),
        "phase": "searching",
    }
