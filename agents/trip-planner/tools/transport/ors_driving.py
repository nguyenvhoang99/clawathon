from __future__ import annotations

import json
import math
import os
from pathlib import Path

import httpx

from tools.geo import CityLocation, _load_json, normalize_city_key

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


class OrsDrivingProvider:
    def estimate(
        self,
        origin: CityLocation,
        destination: CityLocation,
        headcount: int,
    ) -> dict:
        api_key = os.environ.get("ORS_API_KEY")
        price_bands = _load_json("vn_price_bands.json")
        fuel_per_km = price_bands["fuel_vnd_per_km"]
        people_per_car = price_bands["people_per_car"]
        cars = math.ceil(headcount / people_per_car)

        distance_km = self._driving_distance_km(origin, destination, api_key)
        if distance_km is None:
            distance_km = self._fallback_distance(origin, destination)

        duration_hours = distance_km / 55.0
        cost = int(distance_km * fuel_per_km * cars * 2)  # round trip fuel estimate

        return {
            "mode": "drive",
            "distance_km": round(distance_km, 1),
            "duration_hours_one_way": round(duration_hours, 1),
            "cars_needed": cars,
            "cost_vnd": {"low": int(cost * 0.9), "mid": cost, "high": int(cost * 1.2)},
            "notes": f"{cars} car(s), round-trip fuel estimate",
            "source": "ors" if api_key and distance_km else "estimate",
        }

    def _driving_distance_km(
        self, origin: CityLocation, destination: CityLocation, api_key: str | None
    ) -> float | None:
        if not api_key:
            return None
        url = "https://api.openrouteservice.org/v2/directions/driving-car"
        headers = {"Authorization": api_key}
        body = {
            "coordinates": [
                [origin.longitude, origin.latitude],
                [destination.longitude, destination.latitude],
            ]
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(url, headers=headers, json=body)
                response.raise_for_status()
                routes = response.json().get("routes", [])
                if routes:
                    meters = routes[0]["summary"]["distance"]
                    return meters / 1000.0
        except httpx.HTTPError:
            return None
        return None

    def _fallback_distance(self, origin: CityLocation, destination: CityLocation) -> float:
        """Haversine rough distance with road factor."""
        lat1, lon1 = math.radians(origin.latitude), math.radians(origin.longitude)
        lat2, lon2 = math.radians(destination.latitude), math.radians(destination.longitude)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        km = 6371 * 2 * math.asin(math.sqrt(a))
        return km * 1.3


class VnStaticTransportProvider:
    def __init__(self) -> None:
        with open(DATA_DIR / "vn_flight_estimates.json", encoding="utf-8") as handle:
            self._data = json.load(handle)

    def estimate_flight(
        self, origin: CityLocation, destination: CityLocation, headcount: int
    ) -> dict:
        route_key = self._route_key(origin.name, destination.name)
        routes = self._data.get("routes", {})
        route = routes.get(route_key)
        if not route:
            return {
                "mode": "fly",
                "available": False,
                "notes": f"No static flight estimate for {route_key}",
                "source": "estimate",
            }
        per_person = route
        total = {
            tier: per_person[tier] * headcount
            for tier in ("low", "mid", "high")
        }
        return {
            "mode": "fly",
            "available": True,
            "route": route["label"],
            "duration_hours": route["duration_hours"],
            "cost_vnd_per_person": {
                "low": per_person["low"],
                "mid": per_person["mid"],
                "high": per_person["high"],
            },
            "cost_vnd_total": total,
            "source": self._data.get("source", "estimate"),
        }

    def estimate_train(
        self, origin: CityLocation, destination: CityLocation, headcount: int
    ) -> dict:
        route_key = self._route_key(origin.name, destination.name)
        trains = self._data.get("train_estimates", {})
        route = trains.get(route_key) or trains.get(f"{route_key.split('-')[1]}-{route_key.split('-')[0]}")
        if not route:
            return {"mode": "train", "available": False, "source": "estimate"}
        return {
            "mode": "train",
            "available": True,
            "duration_hours": route["duration_hours"],
            "cost_vnd_per_person": {
                "low": route["low"],
                "mid": route["mid"],
                "high": route["high"],
            },
            "cost_vnd_total": {
                tier: route[tier] * headcount for tier in ("low", "mid", "high")
            },
            "source": "estimate",
        }

    def _route_key(self, origin: str, destination: str) -> str:
        codes = self._data.get("city_codes", {})
        o = codes.get(normalize_city_key(origin), "XXX")
        d = codes.get(normalize_city_key(destination), "YYY")
        return f"{o}-{d}"


def estimate_transport(
    origin: CityLocation, destination: CityLocation, headcount: int
) -> dict:
    driving = OrsDrivingProvider().estimate(origin, destination, headcount)
    static = VnStaticTransportProvider()
    flight = static.estimate_flight(origin, destination, headcount)
    train = static.estimate_train(origin, destination, headcount)

    options = [driving]
    if flight.get("available"):
        options.append(flight)
    if train.get("available"):
        options.append(train)

    recommended = min(
        options,
        key=lambda o: o.get("cost_vnd", o.get("cost_vnd_total", {})).get("mid", 10**12)
        if isinstance(o.get("cost_vnd", o.get("cost_vnd_total")), dict)
        else 10**12,
    )

    return {
        "origin": origin.display_name,
        "destination": destination.display_name,
        "headcount": headcount,
        "options": options,
        "recommended_mode": recommended.get("mode"),
        "source": "mixed",
    }
