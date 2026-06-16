from __future__ import annotations

from tools.geo import CityLocation
from tools.overpass_client import overpass_query


def _stay_type(tags: dict) -> str:
    tourism = tags.get("tourism", "hotel")
    stars = tags.get("stars")
    if stars:
        try:
            star_num = int(float(stars))
            return f"hotel_{star_num}star"
        except ValueError:
            pass
    mapping = {
        "hostel": "hostel",
        "guest_house": "guest_house",
        "motel": "guest_house",
        "hotel": "hotel_3star",
    }
    return mapping.get(tourism, "default")


class OsmOverpassStayProvider:
    def search_stays(
        self, location: CityLocation, radius_km: float = 5.0, limit: int = 10
    ) -> dict:
        radius_m = int(radius_km * 1000)
        query = f"""
[out:json][timeout:25];
(
  node["tourism"~"hotel|guest_house|hostel|motel"](around:{radius_m},{location.latitude},{location.longitude});
  way["tourism"~"hotel|guest_house|hostel|motel"](around:{radius_m},{location.latitude},{location.longitude});
);
out center {limit * 3};
"""
        elements = overpass_query(query)
        stays = []
        for element in elements:
            tags = element.get("tags", {})
            name = tags.get("name") or tags.get("name:en")
            if not name:
                continue
            lat = element.get("lat") or element.get("center", {}).get("lat")
            lon = element.get("lon") or element.get("center", {}).get("lon")
            stays.append(
                {
                    "name": name,
                    "type": _stay_type(tags),
                    "stars": tags.get("stars"),
                    "tourism": tags.get("tourism", "hotel"),
                    "lat": lat,
                    "lon": lon,
                    "address": tags.get("addr:street", ""),
                }
            )
            if len(stays) >= limit:
                break

        areas = _suggest_areas(location.name, stays)
        return {
            "city": location.display_name,
            "stays": stays,
            "suggested_areas": areas,
            "count": len(stays),
            "source": "osm",
        }


def _suggest_areas(city: str, stays: list[dict]) -> list[str]:
    city_lower = city.lower()
    defaults = {
        "da nang": ["My Khe Beach", "Han River / City Center", "Son Tra Peninsula"],
        "nha trang": ["Tran Phu Beach", "City Center", "Vinpearl area"],
        "hanoi": ["Old Quarter", "Tay Ho", "Ba Dinh"],
        "ho chi minh": ["District 1", "District 3", "Thu Duc"],
        "phu quoc": ["Duong Dong", "Long Beach", "An Thoi"],
        "hue": ["Imperial City area", "Perfume River", "Lang Co (day trip)"],
    }
    for key, areas in defaults.items():
        if key in city_lower:
            return areas
    return ["City center", "Popular tourist district"] if stays else ["City center"]


def get_stay_provider() -> OsmOverpassStayProvider:
    return OsmOverpassStayProvider()
