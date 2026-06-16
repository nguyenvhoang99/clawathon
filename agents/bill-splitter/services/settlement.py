from __future__ import annotations

import os

from models.member import MemberProfile
from models.session import BillSession
from models.settlement import SettlementResult, SettlementTransfer
from services.ledger import ExpenseLedger
from services.vietqr import build_vietqr_url, fetch_vietqr_base64, sanitize_transfer_content


def simplify_debts(balances: dict[str, int]) -> list[tuple[str, str, int]]:
    debtors = [(m, -b) for m, b in balances.items() if b < 0]
    creditors = [(m, b) for m, b in balances.items() if b > 0]
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)
    transfers: list[tuple[str, str, int]] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor_id, debt_amt = debtors[i]
        creditor_id, credit_amt = creditors[j]
        amount = min(debt_amt, credit_amt)
        if amount > 0:
            transfers.append((debtor_id, creditor_id, amount))
        debtors[i] = (debtor_id, debt_amt - amount)
        creditors[j] = (creditor_id, credit_amt - amount)
        if debtors[i][1] <= 0:
            i += 1
        if creditors[j][1] <= 0:
            j += 1
    return transfers


class SettlementEngine:
    def __init__(self, ledger: ExpenseLedger | None = None) -> None:
        self._ledger = ledger or ExpenseLedger()

    def finalize(
        self,
        session: BillSession,
        *,
        include_base64: bool = False,
    ) -> SettlementResult:
        missing = self._ledger.missing_for_finalize(session)
        if missing:
            raise ValueError(f"Cannot finalize: {', '.join(missing)}")

        member_balances = self._ledger.compute_balances(session)
        net_map = {mid: b.net_vnd for mid, b in member_balances.items()}
        template = os.environ.get("VIETQR_TEMPLATE", "compact2")

        raw_transfers = simplify_debts(net_map)
        transfers: list[SettlementTransfer] = []
        for from_id, to_id, amount in raw_transfers:
            creditor: MemberProfile = session.members[to_id]
            debtor: MemberProfile = session.members[from_id]
            content = sanitize_transfer_content(
                f"Trip {debtor.display_name} to {creditor.display_name}"
            )
            url = build_vietqr_url(
                bank_bin=creditor.bank_bin or "",
                account_no=creditor.account_no or "",
                account_name=creditor.account_name or creditor.display_name,
                amount_vnd=amount,
                transfer_content=content,
                template=template,
            )
            b64 = fetch_vietqr_base64(url) if include_base64 else None
            transfers.append(
                SettlementTransfer(
                    from_member=from_id,
                    from_display_name=debtor.display_name,
                    to_member=to_id,
                    to_display_name=creditor.display_name,
                    amount_vnd=amount,
                    vietqr_url=url,
                    transfer_content=content,
                    vietqr_base64=b64,
                )
            )

        summary = (
            f"{len(transfers)} transfer(s) required to settle the trip."
            if transfers
            else "All balances are even — no transfers needed."
        )
        return SettlementResult(
            balances=member_balances,
            transfers=transfers,
            summary=summary,
        )
