from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from models.expense import Expense
from models.member import MemberProfile


class SessionStatus(str, Enum):
    COLLECTING = "collecting"
    READY_TO_SETTLE = "ready_to_settle"
    SETTLED = "settled"


class BillSession(BaseModel):
    team_id: str
    session_id: str
    members: dict[str, MemberProfile] = Field(default_factory=dict)
    expenses: list[Expense] = Field(default_factory=list)
    status: SessionStatus = SessionStatus.COLLECTING
    settlement_result: dict | None = None

    def member_ids(self) -> list[str]:
        return list(self.members.keys())

    def confirmed_expenses(self) -> list[Expense]:
        return [e for e in self.expenses if e.status.value == "confirmed"]
