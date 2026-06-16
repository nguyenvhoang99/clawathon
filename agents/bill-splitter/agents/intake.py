from __future__ import annotations

import re

from models.session import BillSession


def parse_split_hint(message: str, session: BillSession) -> list[str] | None:
    """Parse hints like 'except Linh' or 'split among alice and bob'."""
    if not message:
        return None
    lower = message.lower()
    all_ids = session.member_ids()
    if not all_ids:
        return None

    if "except" in lower or "excluding" in lower:
        excluded: set[str] = set()
        for member_id, member in session.members.items():
            name = member.display_name.lower()
            if name in lower or member_id.lower() in lower:
                if f"except {name}" in lower or f"except {member_id}" in lower:
                    excluded.add(member_id)
                for part in re.split(r"\bexcept\b", lower, maxsplit=1):
                    if part and (name in part or member_id.lower() in part):
                        excluded.add(member_id)
        for member_id, member in session.members.items():
            name = member.display_name.lower()
            tail = lower.split("except", 1)[-1] if "except" in lower else ""
            if name in tail or member_id.lower() in tail:
                excluded.add(member_id)
        if excluded:
            return [m for m in all_ids if m not in excluded]

    mentioned = [
        mid for mid, m in session.members.items()
        if m.display_name.lower() in lower or mid.lower() in lower
    ]
    if len(mentioned) >= 2:
        return mentioned

    if "everyone" in lower or "all" in lower:
        return all_ids

    return None


def suggest_action(message: str) -> str | None:
    lower = (message or "").lower()
    if any(w in lower for w in ("register", "join", "add member")):
        return "register_member"
    if "bank" in lower or "account" in lower:
        return "set_bank"
    if "finalize" in lower or "settle" in lower:
        return "finalize"
    if "balance" in lower:
        return "list_balances"
    if "list" in lower and "expense" in lower:
        return "list_expenses"
    return None
