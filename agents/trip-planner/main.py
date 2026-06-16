from __future__ import annotations

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext

load_dotenv()

app = GreenNodeAgentBaseApp()

LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
if not LLM_MODEL or not LLM_BASE_URL or not LLM_API_KEY:
    raise ValueError(
        "LLM_MODEL, LLM_BASE_URL, and LLM_API_KEY are required. "
        "Set them in .env or use /agentbase-llm."
    )

llm = ChatOpenAI(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

from graph.orchestrator import build_graph  # noqa: E402

graph = build_graph(llm)

_TRIP_CACHE: dict[str, dict] = {}


def _team_key(context: RequestContext) -> str:
    headers = context.request_headers or {}
    team = headers.get("X-GreenNode-AgentBase-Custom-Team-Id", "default-team")
    session = context.session_id or "default-session"
    return f"{team}:{session}"


def _load_cached_brief(key: str) -> dict:
    if key in _TRIP_CACHE:
        return _TRIP_CACHE[key]
    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        return {}
    try:
        from greennode_agentbase import MemoryClient

        client = MemoryClient()
        actor, session = key.split(":", 1)
        events = client.list_events(memory_id=memory_id, actor_id=actor, session_id=session)
        for event in reversed(events or []):
            content = event.get("content") if isinstance(event, dict) else getattr(event, "content", None)
            if not content:
                continue
            try:
                payload = json.loads(content)
                if isinstance(payload, dict) and "trip_brief" in payload:
                    return payload["trip_brief"]
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return {}


def _save_brief(key: str, brief: dict) -> None:
    _TRIP_CACHE[key] = brief
    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        return
    try:
        from greennode_agentbase import MemoryClient
        from greennode_agentbase.memory.models import ChatMessage, EventCreateRequest

        client = MemoryClient()
        actor, session = key.split(":", 1)
        client.create_event(
            memory_id=memory_id,
            actor_id=actor,
            session_id=session,
            request=EventCreateRequest(
                messages=[
                    ChatMessage(
                        role="assistant",
                        content=json.dumps({"trip_brief": brief}, default=str),
                    )
                ]
            ),
        )
    except Exception:
        pass


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    message = payload.get("message", "")
    cache_key = _team_key(context)
    team_id = (context.request_headers or {}).get(
        "X-GreenNode-AgentBase-Custom-Team-Id", "default-team"
    )

    prior_brief = _load_cached_brief(cache_key)
    if payload.get("trip_brief"):
        prior_brief = payload["trip_brief"]

    initial_state = {
        "user_message": message,
        "team_id": team_id,
        "session_id": context.session_id,
        "trip_brief": prior_brief,
        "data_sources": [],
    }

    result = graph.invoke(initial_state)

    if result.get("trip_brief"):
        _save_brief(cache_key, result["trip_brief"])

    response_body = {
        "status": "success",
        "response": result.get("response", ""),
        "phase": result.get("phase"),
        "timestamp": datetime.now().isoformat(),
        "session_id": context.session_id,
        "team_id": team_id,
    }
    if result.get("trip_brief"):
        response_body["trip_brief"] = result["trip_brief"]
    if result.get("budget_ledger"):
        response_body["budget_ledger"] = result["budget_ledger"]
    if result.get("itinerary"):
        response_body["itinerary"] = result["itinerary"]
    if result.get("data_sources"):
        response_body["data_sources"] = result["data_sources"]
    if result.get("stay_results") and result.get("phase") == "done":
        response_body["stay_results"] = result["stay_results"]
        response_body["transport_results"] = result.get("transport_results")
        response_body["activity_results"] = result.get("activity_results")
        response_body["weather_results"] = result.get("weather_results")

    return response_body


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
