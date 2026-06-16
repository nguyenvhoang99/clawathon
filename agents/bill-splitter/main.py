from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext
from services.router import ActionRouter

load_dotenv()

app = GreenNodeAgentBaseApp()

LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_VISION_MODEL = os.environ.get("LLM_VISION_MODEL") or LLM_MODEL

if not LLM_MODEL or not LLM_BASE_URL or not LLM_API_KEY:
    raise ValueError(
        "LLM_MODEL, LLM_BASE_URL, and LLM_API_KEY are required. "
        "Set them in .env or use /agentbase-llm."
    )

text_llm = ChatOpenAI(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
vision_llm = ChatOpenAI(model=LLM_VISION_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
router = ActionRouter(text_llm, vision_llm)


def _team_id(context: RequestContext) -> str:
    headers = context.request_headers or {}
    return headers.get("X-GreenNode-AgentBase-Custom-Team-Id", "default-team")


def _session_id(context: RequestContext) -> str:
    return context.session_id or "default-session"


def _user_id(context: RequestContext) -> str:
    return context.user_id or "anonymous"


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    result = router.handle(
        payload,
        team_id=_team_id(context),
        session_id=_session_id(context),
        user_id=_user_id(context),
    )
    result["timestamp"] = datetime.now().isoformat()
    return result


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080, host="0.0.0.0")
