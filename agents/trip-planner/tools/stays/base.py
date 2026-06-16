from __future__ import annotations

from typing import Protocol

from tools.geo import CityLocation


class StayProvider(Protocol):
    def search_stays(
        self, location: CityLocation, radius_km: float = 5.0, limit: int = 10
    ) -> dict: ...


class TransportProvider(Protocol):
    def estimate(
        self,
        origin: CityLocation,
        destination: CityLocation,
        headcount: int,
    ) -> dict: ...
