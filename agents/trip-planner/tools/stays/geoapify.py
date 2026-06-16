"""Geoapify stay provider stub — enable when GEOAPIFY_API_KEY is set."""

from __future__ import annotations

import os

from tools.geo import CityLocation


class GeoapifyStayProvider:
    def search_stays(
        self, location: CityLocation, radius_km: float = 5.0, limit: int = 10
    ) -> dict:
        api_key = os.environ.get("GEOAPIFY_API_KEY")
        if not api_key:
            return {
                "error": "GEOAPIFY_API_KEY not configured",
                "source": "geoapify",
                "stays": [],
            }
        # Provider slot for Phase 3 — fall back to OSM in orchestrator
        return {"source": "geoapify", "stays": [], "note": "Not implemented — use STAY_PROVIDER=osm"}
