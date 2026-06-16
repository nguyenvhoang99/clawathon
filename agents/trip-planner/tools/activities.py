from __future__ import annotations

from tools.geo import CityLocation
from tools.overpass_client import overpass_query

PREFERENCE_TAGS = {
    "beach": ("natural=beach", "leisure=beach_resort"),
    "food": ("amenity=restaurant", "tourism=attraction"),
    "hiking": ("route=hiking", "natural=peak"),
    "culture": ("tourism=museum", "historic=castle", "historic=monument"),
    "nightlife": ("amenity=bar", "amenity=nightclub"),
    "nature": ("leisure=park", "natural=waterfall"),
}


def search_activities(
    location: CityLocation,
    preferences: list[str],
    limit: int = 10,
    radius_km: float = 8.0,
) -> dict:
    radius_m = int(radius_km * 1000)
    pref_keys = [p.lower() for p in preferences] or ["culture", "food", "beach"]
    seen_names: set[str] = set()
    activities: list[dict] = []

    for pref in pref_keys:
        tags = PREFERENCE_TAGS.get(pref, PREFERENCE_TAGS["culture"])
        for tag in tags:
            key, value = tag.split("=", 1)
            query = f"""
[out:json][timeout:25];
(
  node["{key}"="{value}"](around:{radius_m},{location.latitude},{location.longitude});
  way["{key}"="{value}"](around:{radius_m},{location.latitude},{location.longitude});
);
out center 15;
"""
            elements = overpass_query(query)
            for element in elements:
                tags_map = element.get("tags", {})
                name = tags_map.get("name") or tags_map.get("name:en")
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                activities.append(
                    {
                        "name": name,
                        "category": pref,
                        "tourism": tags_map.get("tourism"),
                        "fee": tags_map.get("fee", "unknown"),
                        "indoor": pref in ("food", "culture", "nightlife")
                        or tags_map.get("tourism") == "museum",
                    }
                )
                if len(activities) >= limit:
                    break
            if len(activities) >= limit:
                break
        if len(activities) >= limit:
            break

    return {
        "city": location.display_name,
        "activities": activities[:limit],
        "count": min(len(activities), limit),
        "source": "osm",
    }
