from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


@dataclass
class CityLocation:
    name: str
    latitude: float
    longitude: float
    country: str = "Vietnam"
    display_name: str = ""


@lru_cache(maxsize=64)
def _load_json(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as handle:
        return json.load(handle)


def resolve_city(city: str) -> CityLocation | None:
    """Resolve a city name to coordinates using Open-Meteo geocoding."""
    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 5, "language": "en", "format": "json"},
        )
        response.raise_for_status()
        results = response.json().get("results") or []

    for item in results:
        country = item.get("country", "")
        if "Vietnam" in country or country == "VN":
            return CityLocation(
                name=item.get("name", city),
                latitude=item["latitude"],
                longitude=item["longitude"],
                country=country,
                display_name=f"{item.get('name', city)}, {country}",
            )

    if results:
        item = results[0]
        return CityLocation(
            name=item.get("name", city),
            latitude=item["latitude"],
            longitude=item["longitude"],
            country=item.get("country", ""),
            display_name=f"{item.get('name', city)}, {item.get('country', '')}",
        )
    return None


def normalize_city_key(city: str) -> str:
    return city.strip().lower().replace("ho chi minh", "ho chi minh city")
