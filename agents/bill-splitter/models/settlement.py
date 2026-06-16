from __future__ import annotations

from pydantic import BaseModel, Field


class MemberBalance(BaseModel):
    member_id: str
    display_name: str
    paid_vnd: int
    owed_vnd: int
    net_vnd: int
    account_no: str | None = None
    bank_bin: str | None = None


class SettlementTransfer(BaseModel):
    from_member: str
    from_display_name: str
    to_member: str
    to_display_name: str
    amount_vnd: int
    vietqr_url: str
    transfer_content: str
    vietqr_base64: str | None = None


class SettlementResult(BaseModel):
    balances: dict[str, MemberBalance]
    transfers: list[SettlementTransfer] = Field(default_factory=list)
    summary: str = ""
