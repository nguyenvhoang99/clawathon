from __future__ import annotations

import time

import httpx

from tools.geo import OVERPASS_URL

OVERPASS_HEADERS = {
    "User-Agent": "clawathon-trip-planner/1.0",
    "Accept": "application/json",
}


def overpass_query(query: str) -> list[dict]:
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                OVERPASS_URL,
                content=query,
                headers={**OVERPASS_HEADERS, "Content-Type": "text/plain; charset=utf-8"},
            )
            if response.status_code == 429:
                time.sleep(2)
                response = client.post(
                    OVERPASS_URL,
                    content=query,
                    headers={**OVERPASS_HEADERS, "Content-Type": "text/plain; charset=utf-8"},
                )
            response.raise_for_status()
            return response.json().get("elements", [])
    except httpx.HTTPError:
        return []
