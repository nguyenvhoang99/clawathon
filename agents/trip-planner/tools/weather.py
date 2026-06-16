from __future__ import annotations

from tools.geo import CityLocation

WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

RAIN_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
STORM_CODES = {95, 96, 99}


def weather_label(code: int) -> str:
    return WEATHER_CODES.get(code, f"weather code {code}")


def fetch_weather_forecast(location: CityLocation, days: int) -> dict:
    import httpx

    days = max(1, min(days, 16))
    with httpx.Client(timeout=15.0) as client:
        response = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location.latitude,
                "longitude": location.longitude,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        response.raise_for_status()
        payload = response.json()

    daily = payload["daily"]
    day_forecasts = []
    for index, day in enumerate(daily["time"]):
        code = daily["weather_code"][index]
        precip = daily["precipitation_sum"][index]
        rain_likely = code in RAIN_CODES or precip >= 5.0
        outdoor_ok = not rain_likely and code not in STORM_CODES
        day_forecasts.append(
            {
                "date": day,
                "condition": weather_label(code),
                "weather_code": code,
                "temp_high_c": daily["temperature_2m_max"][index],
                "temp_low_c": daily["temperature_2m_min"][index],
                "precipitation_mm": precip,
                "outdoor_ok": outdoor_ok,
                "rain_likely": rain_likely,
            }
        )

    alerts = [
        f"{d['date']}: {d['condition']} — consider indoor activities"
        for d in day_forecasts
        if d["rain_likely"]
    ]

    return {
        "city": location.display_name or location.name,
        "days": day_forecasts,
        "alerts": alerts,
        "source": "open-meteo",
    }
