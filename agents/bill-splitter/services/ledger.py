from __future__ import annotations

import uuid

from models.expense import Expense, ExpenseCategory, ExpenseStatus, LineItem
from models.member import MemberProfile
from models.session import BillSession, SessionStatus
from models.settlement import MemberBalance


class ExpenseLedger:
    def register_member(self, session: BillSession, member: MemberProfile) -> None:
        session.members[member.member_id] = member

    def update_bank(self, session: BillSession, member_id: str, **fields: str) -> MemberProfile:
        member = session.members[member_id]
        updated = member.model_copy(update={k: v for k, v in fields.items() if v is not None})
        session.members[member_id] = updated
        return updated

    def assert_no_duplicate_receipt(self, session: BillSession, receipt_hash: str) -> None:
        if any(e.receipt_image_hash == receipt_hash for e in session.expenses):
            raise ValueError("Receipt image already uploaded for this session")

    def add_expense(self, session: BillSession, expense: Expense) -> Expense:
        session.expenses.append(expense)
        return expense

    def get_expense(self, session: BillSession, expense_id: str) -> Expense | None:
        return next((e for e in session.expenses if e.expense_id == expense_id), None)

    def confirm_expense(
        self,
        session: BillSession,
        expense_id: str,
        *,
        total_vnd: int | None = None,
        category: ExpenseCategory | None = None,
        merchant: str | None = None,
        payer_id: str | None = None,
    ) -> Expense:
        expense = self.get_expense(session, expense_id)
        if not expense:
            raise ValueError(f"Expense not found: {expense_id}")
        updates: dict = {"status": ExpenseStatus.CONFIRMED}
        if total_vnd is not None:
            updates["total_vnd"] = total_vnd
        if category is not None:
            updates["category"] = category
        if merchant is not None:
            updates["merchant"] = merchant
        if payer_id is not None:
            updates["payer_id"] = payer_id
        if not expense.split_among:
            updates["split_among"] = session.member_ids()
        idx = session.expenses.index(expense)
        session.expenses[idx] = expense.model_copy(update=updates)
        return session.expenses[idx]

    def assign_split(
        self,
        session: BillSession,
        expense_id: str,
        member_ids: list[str],
        payer_id: str | None = None,
    ) -> Expense:
        expense = self.get_expense(session, expense_id)
        if not expense:
            raise ValueError(f"Expense not found: {expense_id}")
        for mid in member_ids:
            if mid not in session.members:
                raise ValueError(f"Unknown member: {mid}")
        updates: dict = {"split_among": member_ids}
        if payer_id:
            updates["payer_id"] = payer_id
        idx = session.expenses.index(expense)
        session.expenses[idx] = expense.model_copy(update=updates)
        return session.expenses[idx]

    def add_manual_expense(
        self,
        session: BillSession,
        *,
        uploaded_by: str,
        payer_id: str,
        total_vnd: int,
        category: ExpenseCategory,
        split_among: list[str],
        merchant: str | None = None,
        line_items: list[LineItem] | None = None,
        confirm: bool = True,
    ) -> Expense:
        expense = Expense(
            expense_id=str(uuid.uuid4())[:8],
            uploaded_by=uploaded_by,
            payer_id=payer_id,
            merchant=merchant,
            category=category,
            total_vnd=total_vnd,
            line_items=line_items or [],
            split_among=split_among,
            status=ExpenseStatus.CONFIRMED if confirm else ExpenseStatus.DRAFT,
            extracted_confidence=1.0,
        )
        return self.add_expense(session, expense)

    def compute_balances(self, session: BillSession) -> dict[str, MemberBalance]:
        paid: dict[str, int] = {mid: 0 for mid in session.members}
        owed: dict[str, int] = {mid: 0 for mid in session.members}

        for expense in session.confirmed_expenses():
            if expense.payer_id in paid:
                paid[expense.payer_id] += expense.total_vnd
            participants = expense.split_among or session.member_ids()
            if not participants:
                continue
            share = expense.total_vnd // len(participants)
            remainder = expense.total_vnd - share * len(participants)
            for i, member_id in enumerate(participants):
                if member_id in owed:
                    owed[member_id] += share + (1 if i < remainder else 0)

        balances = {}
        for member_id, member in session.members.items():
            p = paid.get(member_id, 0)
            o = owed.get(member_id, 0)
            balances[member_id] = MemberBalance(
                member_id=member_id,
                display_name=member.display_name,
                paid_vnd=p,
                owed_vnd=o,
                net_vnd=p - o,
                account_no=member.account_no,
                bank_bin=member.bank_bin,
            )
        return balances

    def confirm_bills(self, session: BillSession) -> None:
        """Mark session ready to settle after all bills are confirmed."""
        if session.status == SessionStatus.SETTLED:
            raise ValueError("Session already settled")
        if not session.confirmed_expenses():
            raise ValueError("No confirmed expenses — add and confirm bills first")
        drafts = [e for e in session.expenses if e.status == ExpenseStatus.DRAFT]
        if drafts:
            raise ValueError(f"{len(drafts)} draft expense(s) still need confirmation")

        involved: set[str] = set()
        for expense in session.confirmed_expenses():
            involved.update(expense.split_among)
            involved.add(expense.payer_id)

        for member_id in involved:
            if member_id not in session.members:
                raise ValueError(f"Member not registered: {member_id}")
            member = session.members[member_id]
            if not member.has_bank_details():
                raise ValueError(f"Missing bank details for {member.display_name}")

        session.status = SessionStatus.READY_TO_SETTLE

    def missing_for_finalize(self, session: BillSession) -> list[str]:
        missing: list[str] = []
        if not session.confirmed_expenses():
            missing.append("expenses:need_at_least_one_confirmed")
        if session.status == SessionStatus.SETTLED:
            missing.append("session:already_settled")

        drafts = [e for e in session.expenses if e.status == ExpenseStatus.DRAFT]
        if drafts:
            missing.append("expenses:drafts_need_confirmation")

        if session.status == SessionStatus.COLLECTING and not drafts:
            # Backward-compatible: allow finalize without explicit confirm_bills
            pass
        elif session.status != SessionStatus.READY_TO_SETTLE:
            missing.append("session:not_ready_to_settle")

        involved: set[str] = set()
        for expense in session.confirmed_expenses():
            involved.update(expense.split_among)
            involved.add(expense.payer_id)

        for member_id in involved:
            if member_id not in session.members:
                missing.append(f"member:{member_id}:not_registered")

        balances = self.compute_balances(session)
        for member_id, balance in balances.items():
            if balance.net_vnd > 0:
                member = session.members.get(member_id)
                if not member or not member.has_bank_details():
                    missing.append(f"member:{member_id}:bank_details")
        return missing
