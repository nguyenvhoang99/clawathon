from __future__ import annotations

from pydantic import BaseModel, Field


class MemberProfile(BaseModel):
    member_id: str
    display_name: str
    bank_bin: str | None = None
    bank_code: str | None = None
    account_no: str | None = None
    account_name: str | None = None

    def has_bank_details(self) -> bool:
        return bool(self.bank_bin and self.account_no and self.account_name)
