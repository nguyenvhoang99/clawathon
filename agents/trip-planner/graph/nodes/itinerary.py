from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from models.trip_brief import TripBrief, TripStatus
from services.plan_builder import build_plan


ITINERARY_PROMPT = """Bạn là chuyên gia lên kế hoạch team trip tại Việt Nam cho nhóm bạn trẻ (20–35 tuổi).
Bạn nhận một JSON gồm `plan.overall`, `plan.spending`, `plan.activities` đã có sẵn dữ liệu xác định.
Nhiệm vụ của bạn là tinh chỉnh kế hoạch và TRẢ VỀ JSON DUY NHẤT theo schema sau:

{
  "summary": "1 đoạn ngắn (3–5 câu) tổng quan chuyến đi bằng tiếng Việt, nêu rõ:
              số người, khoảng thời gian, ngày diễn ra hoạt động team building chính,
              và khoảng ngân sách dự kiến/người. Không markdown, không bullet.",
  "mainTeamBuildingDay": {
    "day": <số ngày, 1-based>,
    "date": "<YYYY-MM-DD hoặc null>",
    "activity": "<tên hoạt động chính>",
    "reason": "<lý do chọn ngày này, ngắn gọn bằng tiếng Việt>"
  },
  "days": [
    {
      "day": <int>,
      "date": "<YYYY-MM-DD hoặc null>",
      "title": "<tên chủ đề ngày, vd: Ngày khám phá biển>",
      "activities": [
        {"name": "<tên>", "category": "<beach|food|nightlife|culture|nature|adventure>",
         "timeOfDay": "morning|afternoon|evening|night",
         "description": "<mô tả 1 câu, hợp gu các bạn trẻ>"}
      ],
      "note": "<lưu ý ngắn về trang phục hoặc di chuyển, không nhắc thời tiết>"
    }
  ],
  "tips": ["<3-5 mẹo ngắn cho nhóm bạn trẻ, mỗi mẹo 1 câu, không bullet>"]
}

QUY TẮC BẮT BUỘC:
- Chỉ trả về JSON hợp lệ, không thêm markdown, code fence, hay văn bản ngoài JSON.
- HOÀN TOÀN bằng tiếng Việt, KHÔNG dùng **, *, #, _, backtick.
- Mỗi ngày có 2–3 hoạt động lấy từ `plan.activities.pool` hoặc kết hợp với hiểu biết của bạn về điểm đến.
- Hoạt động phải phù hợp giới trẻ: ẩm thực đường phố, café check-in, biển, leo núi nhẹ, vui chơi giải trí, nhạc sống, chợ đêm…
- Tránh tour cao tuổi (spa nghỉ dưỡng dài, viện bảo tàng lịch sử dày đặc).
- KHÔNG nhắc cảnh báo thời tiết trong summary, tips hay note.
- Mỗi ngày phải KHÁC nhau, không lặp hoạt động.
- Ngày diễn ra team building chính nên trùng với `plan.overall.mainTeamBuildingDay` (có thể đề xuất khác nếu lý do thuyết phục).
- KHÔNG đề xuất đặt vé/khách sạn trong tips (UI đã có phần giá).
"""


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _parse_llm_json(content: str) -> dict | None:
    if not content:
        return None
    cleaned = _strip_code_fence(content)
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _merge_llm_into_plan(plan: dict, llm: dict | None) -> dict:
    if not llm:
        return plan

    overall = plan.setdefault("overall", {})
    if isinstance(llm.get("summary"), str):
        overall["summary"] = llm["summary"].strip()

    if isinstance(llm.get("mainTeamBuildingDay"), dict):
        existing = overall.get("mainTeamBuildingDay") or {}
        merged = {**existing, **{k: v for k, v in llm["mainTeamBuildingDay"].items() if v}}
        overall["mainTeamBuildingDay"] = merged

    if isinstance(llm.get("tips"), list):
        overall["tips"] = [t for t in llm["tips"] if isinstance(t, str) and t.strip()][:6]

    if isinstance(llm.get("days"), list) and llm["days"]:
        activities = plan.setdefault("activities", {})
        merged_days: list[dict] = []
        base_days = {d.get("day"): d for d in activities.get("days") or []}
        for entry in llm["days"]:
            if not isinstance(entry, dict):
                continue
            day_no = entry.get("day")
            base = base_days.get(day_no, {}).copy()
            base.update({k: v for k, v in entry.items() if v is not None})
            if isinstance(entry.get("activities"), list):
                base["activities"] = entry["activities"]
            merged_days.append(base)
        if merged_days:
            activities["days"] = merged_days

    return plan


def _plan_to_text(plan: dict) -> str:
    """Render a plain-text Vietnamese narrative from the merged plan."""
    overall = plan.get("overall", {})
    lines: list[str] = []

    summary = overall.get("summary")
    if summary:
        lines.append("📋 Tổng quan")
        lines.append(summary)
        lines.append("")

    headcount = overall.get("headcount")
    nights = overall.get("nights")
    date_label = overall.get("dateRangeLabel") or ""
    main_day = (overall.get("mainTeamBuildingDay") or {})
    budget = overall.get("budgetRange") or {}
    info = []
    if headcount:
        info.append(f"👥 {headcount} người")
    if nights:
        info.append(f"🗓️ {nights} ngày")
    if date_label:
        info.append(f"📅 {date_label}")
    if main_day.get("day"):
        date_str = f" ({main_day.get('date')})" if main_day.get("date") else ""
        info.append(f"🎯 Team building chính: ngày {main_day['day']}{date_str} — {main_day.get('activity') or ''}")
    if budget.get("low") or budget.get("high"):
        info.append(f"💰 Ngân sách/người: {budget.get('low', 0):,} – {budget.get('high', 0):,} VND")
    if info:
        lines.extend(info)
        lines.append("")

    days = (plan.get("activities") or {}).get("days") or []
    if days:
        lines.append("🗺️ Lịch trình theo ngày")
        for day in days:
            day_no = day.get("day")
            date_str = f" · {day.get('date')}" if day.get("date") else ""
            title = day.get("title") or ""
            header = f"Ngày {day_no}{date_str}"
            if title:
                header += f": {title}"
            lines.append(header)
            for act in day.get("activities") or []:
                tod = act.get("timeOfDay")
                tod_label = {"morning": "Sáng", "afternoon": "Chiều", "evening": "Tối", "night": "Đêm"}.get(tod, "")
                desc = act.get("description") or ""
                name = act.get("name") or ""
                bullet = f"• {tod_label + ' · ' if tod_label else ''}{name}"
                if desc:
                    bullet += f" — {desc}"
                lines.append(bullet)
            note = day.get("note")
            if note:
                lines.append(f"  ↳ {note}")
            lines.append("")

    tips = overall.get("tips") or []
    if tips:
        lines.append("💡 Mẹo cho team")
        for tip in tips:
            lines.append(f"• {tip}")

    return "\n".join(lines).strip()


def itinerary_node(state: dict, llm) -> dict:
    brief = TripBrief(**state["trip_brief"])
    plan = build_plan(state)

    llm_input = {
        "plan": plan,
        "trip_brief": state.get("trip_brief"),
        "weather_results": state.get("weather_results"),
    }

    llm_data: dict | None = None
    try:
        response = llm.invoke(
            [
                SystemMessage(content=ITINERARY_PROMPT),
                HumanMessage(content=json.dumps(llm_input, ensure_ascii=False, default=str)),
            ]
        )
        llm_data = _parse_llm_json(response.content or "")
    except Exception:
        llm_data = None

    plan = _merge_llm_into_plan(plan, llm_data)
    body = _plan_to_text(plan)

    brief.status = TripStatus.DONE

    return {
        "response": body,
        "plan": plan,
        "itinerary": {"days": (plan.get("activities") or {}).get("days") or []},
        "trip_brief": brief.model_dump(mode="json"),
        "phase": "done",
    }
