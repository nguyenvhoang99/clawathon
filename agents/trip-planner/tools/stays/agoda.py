"""Agoda / OTA provider stub — plug in when partner API credentials are available."""

from __future__ import annotations

from tools.geo import CityLocation


class AgodaStayProvider:
    def search_stays(
        self, location: CityLocation, radius_km: float = 5.0, limit: int = 10
    ) -> dict:
        return {
            "source": "api",
            "stays": [],
            "note": "Agoda provider not configured — use price bands from vn_price_bands.json",
        }
