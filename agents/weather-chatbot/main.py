import os
from datetime import datetime

import httpx
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext

load_dotenv()

app = GreenNodeAgentBaseApp()

LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
if not LLM_MODEL or not LLM_BASE_URL or not LLM_API_KEY:
    raise ValueError(
        "LLM_MODEL, LLM_BASE_URL, and LLM_API_KEY environment variables are required. "
        "Set them in your .env file or use /agentbase-llm to get a platform API key."
    )

llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
)

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


def _weather_label(code: int) -> str:
    return WEATHER_CODES.get(code, f"weather code {code}")


@tool
def get_current_weather(city: str) -> str:
    """Get current weather for a city. Pass the city name, e.g. 'Hanoi' or 'Ho Chi Minh City'."""
    with httpx.Client(timeout=15.0) as client:
        geo_resp = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()

        results = geo_data.get("results") or []
        if not results:
            return f"Could not find a location named '{city}'. Try a different spelling."

        location = results[0]
        latitude = location["latitude"]
        longitude = location["longitude"]
        place = f"{location.get('name', city)}, {location.get('country', '')}".strip(", ")

        weather_resp = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        weather_resp.raise_for_status()
        current = weather_resp.json()["current"]

    return (
        f"Current weather in {place}:\n"
        f"- Condition: {_weather_label(current['weather_code'])}\n"
        f"- Temperature: {current['temperature_2m']}°C\n"
        f"- Humidity: {current['relative_humidity_2m']}%\n"
        f"- Wind speed: {current['wind_speed_10m']} km/h"
    )


@tool
def get_weather_forecast(city: str, days: int = 3) -> str:
    """Get a multi-day weather forecast for a city. days should be between 1 and 7."""
    days = max(1, min(days, 7))

    with httpx.Client(timeout=15.0) as client:
        geo_resp = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
        )
        geo_resp.raise_for_status()
        results = geo_resp.json().get("results") or []
        if not results:
            return f"Could not find a location named '{city}'. Try a different spelling."

        location = results[0]
        place = f"{location.get('name', city)}, {location.get('country', '')}".strip(", ")

        weather_resp = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        weather_resp.raise_for_status()
        daily = weather_resp.json()["daily"]

    lines = [f"{days}-day forecast for {place}:"]
    for i, date in enumerate(daily["time"]):
        lines.append(
            f"- {date}: {_weather_label(daily['weather_code'][i])}, "
            f"high {daily['temperature_2m_max'][i]}°C / low {daily['temperature_2m_min'][i]}°C, "
            f"precipitation {daily['precipitation_sum'][i]} mm"
        )
    return "\n".join(lines)


SYSTEM_PROMPT = """You are a friendly weather assistant. Answer weather questions clearly and concisely.

Use your tools to look up real weather data when the user asks about current conditions or forecasts.
If the user asks a general question about weather concepts (e.g. what causes rain), answer from your knowledge.
Always mention the city or location when reporting weather data.
If a city name is ambiguous, ask the user to clarify."""

agent = create_agent(
    llm,
    tools=[get_current_weather, get_weather_forecast],
    system_prompt=SYSTEM_PROMPT,
)


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    message = payload.get("message", "Hello")

    result = agent.invoke({"messages": [{"role": "user", "content": message}]})
    ai_message = result["messages"][-1]
    return {
        "status": "success",
        "response": ai_message.content,
        "timestamp": datetime.now().isoformat(),
        "session_id": context.session_id,
    }


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
