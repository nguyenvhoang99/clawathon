from __future__ import annotations

import asyncio

from models.trip_brief import TripBrief
from tools.activities import search_activities
from tools.geo import resolve_city
from tools.stays.osm_overpass import get_stay_provider
from tools.transport.ors_driving import estimate_transport
from tools.weather import fetch_weather_forecast


async def _run_specialists(brief: TripBrief) -> dict:
    dest = resolve_city(brief.destination_city or "")
    origin = resolve_city(brief.origin_city or "")
    if not dest:
        return {
            "stay_results": {"error": f"Could not resolve {brief.destination_city}"},
            "transport_results": {},
            "activity_results": {},
            "weather_results": {},
            "data_sources": [],
        }

    stay_provider = get_stay_provider()
    nights = brief.nights or 3

    loop = asyncio.get_event_loop()

    async def _safe(coro_fn, default: dict) -> dict:
        try:
            return await coro_fn()
        except Exception as exc:
            default["error"] = str(exc)
            return default

    async def _done(value: dict) -> dict:
        return value

    stay_future = _safe(
        lambda: loop.run_in_executor(None, stay_provider.search_stays, dest),
        {"stays": [], "source": "osm"},
    )
    activity_future = _safe(
        lambda: loop.run_in_executor(
            None, lambda: search_activities(dest, brief.preferences, limit=10)
        ),
        {"activities": [], "source": "osm"},
    )
    weather_future = _safe(
        lambda: loop.run_in_executor(
            None, lambda: fetch_weather_forecast(dest, nights)
        ),
        {"days": [], "source": "open-meteo"},
    )
    transport_future = (
        _safe(
            lambda: loop.run_in_executor(
                None, lambda: estimate_transport(origin, dest, brief.headcount)
            ),
            {"options": [], "source": "estimate"},
        )
        if origin
        else _done({"options": [], "source": "estimate"})
    )

    stay_results, activity_results, weather_results, transport_results = await asyncio.gather(
        stay_future, activity_future, weather_future, transport_future
    )

    sources = list(
        {
            stay_results.get("source"),
            activity_results.get("source"),
            weather_results.get("source"),
            transport_results.get("source"),
        }
        - {None}
    )

    return {
        "stay_results": stay_results,
        "transport_results": transport_results,
        "activity_results": activity_results,
        "weather_results": weather_results,
        "data_sources": sources,
        "phase": "planning",
    }


def specialists_node(state: dict) -> dict:
    brief = TripBrief(**state["trip_brief"])
    result = asyncio.run(_run_specialists(brief))
    return result
