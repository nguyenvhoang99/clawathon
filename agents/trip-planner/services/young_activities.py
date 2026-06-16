"""Curate activities aimed at young adults (20–35) for Vietnamese trip plans.

Combines OSM/Overpass POIs (from `activity_results`) with a small library of
hand-picked young-people destinations per city so the agent always has a
solid pool to pick from when the LLM enriches the day-by-day itinerary.
"""

from __future__ import annotations

import unicodedata

YOUNG_FRIENDLY_TAGS = {"food", "nightlife", "beach", "nature", "culture", "hiking"}


_CITY_LIBRARY: dict[str, list[dict]] = {
    "da nang": [
        {"name": "Bãi biển Mỹ Khê", "category": "beach", "tags": ["beach", "team building"], "indoor": False},
        {"name": "Bán đảo Sơn Trà", "category": "nature", "tags": ["nature", "hiking"], "indoor": False},
        {"name": "Cầu Rồng & Cầu Tình Yêu", "category": "culture", "tags": ["sightseeing", "night"], "indoor": False},
        {"name": "Phố ẩm thực Hải Phòng", "category": "food", "tags": ["food", "street food"], "indoor": False},
        {"name": "Bà Nà Hills · Cầu Vàng", "category": "nature", "tags": ["amusement", "photo"], "indoor": False},
        {"name": "Asia Park · Sun World", "category": "nightlife", "tags": ["amusement", "night"], "indoor": False},
        {"name": "Chợ đêm Sơn Trà", "category": "food", "tags": ["night market", "food"], "indoor": False},
        {"name": "Suối Hoa Đà Nẵng (zipline & tắm suối)", "category": "nature", "tags": ["adventure", "team building"], "indoor": False},
    ],
    "hoi an": [
        {"name": "Phố cổ Hội An về đêm (đèn lồng)", "category": "culture", "tags": ["sightseeing", "night"], "indoor": False},
        {"name": "Thả hoa đăng sông Hoài", "category": "culture", "tags": ["culture", "photo"], "indoor": False},
        {"name": "Làng rau Trà Quế (đạp xe)", "category": "nature", "tags": ["nature", "team building"], "indoor": False},
        {"name": "Bãi biển An Bàng", "category": "beach", "tags": ["beach"], "indoor": False},
    ],
    "ho chi minh city": [
        {"name": "Phố Bùi Viện", "category": "nightlife", "tags": ["nightlife", "bar"], "indoor": False},
        {"name": "Landmark 81 SkyView", "category": "culture", "tags": ["sightseeing", "photo"], "indoor": True},
        {"name": "Phố đi bộ Nguyễn Huệ", "category": "culture", "tags": ["sightseeing", "night"], "indoor": False},
        {"name": "Bảo tàng Mỹ thuật TP.HCM", "category": "culture", "tags": ["museum"], "indoor": True},
        {"name": "Chợ Bến Thành & ẩm thực Quận 1", "category": "food", "tags": ["food", "market"], "indoor": False},
        {"name": "Vạn Phúc Waterpark hoặc Đầm Sen", "category": "nature", "tags": ["team building", "outdoor"], "indoor": False},
    ],
    "hanoi": [
        {"name": "Phố cổ & Hồ Hoàn Kiếm", "category": "culture", "tags": ["sightseeing"], "indoor": False},
        {"name": "Bia hơi Tạ Hiện", "category": "nightlife", "tags": ["nightlife", "food"], "indoor": False},
        {"name": "Train Street (cà phê đường tàu)", "category": "culture", "tags": ["photo", "coffee"], "indoor": False},
        {"name": "Hồ Tây · đạp vịt và đường ven hồ", "category": "nature", "tags": ["team building"], "indoor": False},
        {"name": "Bảo tàng Dân tộc học", "category": "culture", "tags": ["museum"], "indoor": True},
        {"name": "Ninh Bình day-trip (Tràng An)", "category": "nature", "tags": ["adventure", "team building"], "indoor": False},
    ],
    "nha trang": [
        {"name": "Bãi biển Trần Phú", "category": "beach", "tags": ["beach"], "indoor": False},
        {"name": "VinWonders Nha Trang", "category": "nightlife", "tags": ["amusement", "team building"], "indoor": False},
        {"name": "Lặn ngắm san hô Hòn Mun", "category": "nature", "tags": ["adventure", "team building"], "indoor": False},
        {"name": "Tháp Bà Ponagar", "category": "culture", "tags": ["culture"], "indoor": False},
    ],
    "phu quoc": [
        {"name": "Bãi Sao", "category": "beach", "tags": ["beach"], "indoor": False},
        {"name": "Cáp treo Hòn Thơm", "category": "nature", "tags": ["adventure", "photo"], "indoor": False},
        {"name": "Sunset Sanato Beach Club", "category": "nightlife", "tags": ["nightlife", "beach"], "indoor": False},
        {"name": "Chợ đêm Phú Quốc", "category": "food", "tags": ["food", "market"], "indoor": False},
    ],
    "da lat": [
        {"name": "Quảng trường Lâm Viên & Hồ Xuân Hương", "category": "culture", "tags": ["sightseeing"], "indoor": False},
        {"name": "Đồi chè Cầu Đất", "category": "nature", "tags": ["photo"], "indoor": False},
        {"name": "Maze Bar (Hang Nga Crazy House)", "category": "nightlife", "tags": ["nightlife"], "indoor": True},
        {"name": "Thác Datanla zipline & high-rope", "category": "nature", "tags": ["adventure", "team building"], "indoor": False},
    ],
}


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFD", (name or "").lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("-", " ").strip()


def _city_pool(city: str | None) -> list[dict]:
    if not city:
        return []
    key = _normalize(city)
    for alias, items in _CITY_LIBRARY.items():
        if alias in key or key in alias:
            return list(items)
    return []


def _is_young_friendly(activity: dict) -> bool:
    if activity.get("category") in YOUNG_FRIENDLY_TAGS:
        return True
    tourism = (activity.get("tourism") or "").lower()
    return tourism in {"attraction", "viewpoint", "theme_park", "museum"}


def curate_activity_pool(
    destination_city: str | None,
    activity_results: dict | None,
    preferences: list[str] | None = None,
) -> list[dict]:
    """Combine OSM activities + curated young-friendly highlights."""
    pool: list[dict] = []
    seen: set[str] = set()

    for item in _city_pool(destination_city):
        key = _normalize(item["name"])
        if key in seen:
            continue
        seen.add(key)
        pool.append({**item, "source": "curated"})

    osm_activities = (activity_results or {}).get("activities") or []
    for item in osm_activities:
        if not _is_young_friendly(item):
            continue
        name = item.get("name")
        if not name:
            continue
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        pool.append({
            "name": name,
            "category": item.get("category") or "culture",
            "tags": [item.get("category") or "culture"],
            "indoor": bool(item.get("indoor")),
            "source": "osm",
        })

    pref_set = {p.lower() for p in (preferences or [])}
    if pref_set:
        pool.sort(key=lambda a: 0 if a.get("category") in pref_set else 1)

    return pool
