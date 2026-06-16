from __future__ import annotations

import json
import os

from models.session import BillSession

_SESSION_CACHE: dict[str, BillSession] = {}


def session_key(team_id: str, session_id: str) -> str:
    return f"{team_id}:{session_id}"


def load_session(team_id: str, session_id: str) -> BillSession:
    key = session_key(team_id, session_id)
    if key in _SESSION_CACHE:
        return _SESSION_CACHE[key]

    memory_id = os.environ.get("MEMORY_ID")
    if memory_id:
        try:
            from greennode_agentbase import MemoryClient

            client = MemoryClient()
            events = client.list_events(
                memory_id=memory_id, actor_id=team_id, session_id=session_id
            )
            for event in reversed(events or []):
                content = (
                    event.get("content")
                    if isinstance(event, dict)
                    else getattr(event, "content", None)
                )
                if not content:
                    continue
                try:
                    payload = json.loads(content)
                    if isinstance(payload, dict) and "bill_session" in payload:
                        return BillSession.model_validate(payload["bill_session"])
                except (json.JSONDecodeError, ValueError):
                    continue
        except Exception:
            pass

    return BillSession(team_id=team_id, session_id=session_id)


def save_session(session: BillSession) -> None:
    key = session_key(session.team_id, session.session_id)
    _SESSION_CACHE[key] = session

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        return
    try:
        from greennode_agentbase import MemoryClient
        from greennode_agentbase.memory.models import ChatMessage, EventCreateRequest

        client = MemoryClient()
        client.create_event(
            memory_id=memory_id,
            actor_id=session.team_id,
            session_id=session.session_id,
            request=EventCreateRequest(
                messages=[
                    ChatMessage(
                        role="assistant",
                        content=json.dumps(
                            {"bill_session": session.model_dump(mode="json")},
                            default=str,
                        ),
                    )
                ]
            ),
        )
    except Exception:
        pass
