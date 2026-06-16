from __future__ import annotations

from typing import Protocol

from tools.geo import CityLocation


class TransportProvider(Protocol):
    def estimate(
        self,
        origin: CityLocation,
        destination: CityLocation,
        headcount: int,
    ) -> dict: ...
