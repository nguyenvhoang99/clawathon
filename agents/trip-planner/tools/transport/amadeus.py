"""Amadeus flight provider stub for live domestic fares."""

from __future__ import annotations

from tools.geo import CityLocation


class AmadeusTransportProvider:
    def search_flights(
        self, origin: CityLocation, destination: CityLocation, headcount: int, date: str
    ) -> dict:
        return {
            "source": "api",
            "available": False,
            "note": "Configure Amadeus API credentials via /agentbase-identity to enable live fares",
        }
