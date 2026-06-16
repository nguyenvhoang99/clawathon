from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from agents.intake import parse_split_hint, suggest_action
from agents.receipt_vision import (
    apply_form_overrides,
    draft_to_expense,
    extract_receipt,
    image_hash,
    validate_image,
)
from models.expense import Expense, ExpenseCategory
from models.member import MemberProfile
from models.session import BillSession, SessionStatus
from services.ledger import ExpenseLedger
from services.receipt_images import make_thumbnail_base64
from services.settlement import SettlementEngine
from services.storage import load_session, save_session


def expense_to_api(expense: Expense, session: BillSession) -> dict[str, Any]:
    payer = session.members.get(expense.payer_id)
    data = expense.model_dump(mode="json")
    data["payer_display_name"] = payer.display_name if payer else expense.payer_id
    data["has_receipt"] = bool(expense.receipt_thumbnail_base64 or expense.receipt_image_hash)
    return data


class ActionRouter:
    def __init__(self, text_llm: ChatOpenAI, vision_llm: ChatOpenAI) -> None:
        self._text_llm = text_llm
        self._vision_llm = vision_llm
        self._ledger = ExpenseLedger()
        self._settlement = SettlementEngine(self._ledger)

    def handle(
        self,
        payload: dict[str, Any],
        *,
        team_id: str,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        session = load_session(team_id, session_id)
        action = payload.get("action") or suggest_action(payload.get("message", ""))

        if not action:
            return {
                "status": "success",
                "phase": "help",
                "response": (
                    "Specify an action: register_member, set_bank, upload_receipt, "
                    "add_expense, confirm_expense, assign_split, list_expenses, "
                    "list_members, list_balances, confirm_bills, finalize, get_settlement"
                ),
            }

        try:
            result = self._dispatch(action, payload, session, user_id)
        except ValueError as exc:
            return {"status": "error", "phase": session.status.value, "error": str(exc)}

        save_session(session)
        result.setdefault("status", "success")
        result["session_status"] = session.status.value
        result["team_id"] = team_id
        result["session_id"] = session_id
        return result

    def _dispatch(
        self,
        action: str,
        payload: dict[str, Any],
        session: BillSession,
        user_id: str,
    ) -> dict[str, Any]:
        if action == "register_member":
            member_id = payload.get("member_id") or user_id
            member = MemberProfile(
                member_id=member_id,
                display_name=payload.get("display_name") or member_id,
                bank_bin=payload.get("bank_bin"),
                bank_code=payload.get("bank_code"),
                account_no=payload.get("account_no"),
                account_name=payload.get("account_name"),
            )
            self._ledger.register_member(session, member)
            return {
                "phase": "collecting",
                "response": f"Registered member {member.display_name}.",
                "member": member.model_dump(),
            }

        if action == "set_bank":
            member_id = payload.get("member_id") or user_id
            if member_id not in session.members:
                raise ValueError(f"Member not registered: {member_id}")
            member = self._ledger.update_bank(
                session,
                member_id,
                bank_bin=payload.get("bank_bin"),
                bank_code=payload.get("bank_code"),
                account_no=payload.get("account_no"),
                account_name=payload.get("account_name"),
            )
            return {
                "phase": "collecting",
                "response": f"Bank details updated for {member.display_name}.",
                "member": member.model_dump(),
            }

        if action == "add_expense":
            member_id = payload.get("payer_id") or user_id
            split_among = payload.get("member_ids") or payload.get("split_among") or session.member_ids()
            category = ExpenseCategory(payload.get("category", "other"))
            expense = self._ledger.add_manual_expense(
                session,
                uploaded_by=user_id,
                payer_id=member_id,
                total_vnd=int(payload["total_vnd"]),
                category=category,
                split_among=split_among,
                merchant=payload.get("merchant"),
                confirm=True,
            )
            return {
                "phase": "collecting",
                "response": f"Added expense {expense.expense_id}: {expense.total_vnd:,} VND.",
                "expense": expense_to_api(expense, session),
            }

        if action == "upload_receipt":
            image_b64 = payload.get("image_base64")
            media_type = payload.get("image_media_type", "image/jpeg")
            if not image_b64:
                raise ValueError("image_base64 is required for upload_receipt")
            raw = validate_image(image_b64, media_type)
            r_hash = image_hash(raw)
            self._ledger.assert_no_duplicate_receipt(session, r_hash)

            hint = payload.get("message", "") or payload.get("notes", "")
            split_among = (
                payload.get("member_ids")
                or payload.get("split_among")
                or parse_split_hint(hint, session)
            )
            payer_id = payload.get("payer_id") or user_id

            draft = extract_receipt(self._vision_llm, image_b64, media_type, hint)
            draft = apply_form_overrides(draft, payload)

            form_complete = (
                payload.get("total_vnd") is not None
                and bool(payload.get("merchant"))
            )
            thumbnail = make_thumbnail_base64(raw)
            expense = draft_to_expense(
                draft,
                session,
                user_id,
                r_hash,
                split_among,
                payer_id=payer_id,
                receipt_thumbnail_base64=thumbnail,
                force_confirm=form_complete,
            )
            self._ledger.add_expense(session, expense)
            return {
                "phase": "collecting",
                "response": (
                    f"Receipt parsed as {expense.status.value} expense {expense.expense_id}. "
                    f"Total: {expense.total_vnd:,} VND, confidence: {expense.extracted_confidence:.0%}."
                ),
                "expense": expense_to_api(expense, session),
                "needs_confirm": expense.status.value == "draft",
            }

        if action == "confirm_expense":
            expense_id = payload["expense_id"]
            category = payload.get("category")
            expense = self._ledger.confirm_expense(
                session,
                expense_id,
                total_vnd=int(payload["total_vnd"]) if payload.get("total_vnd") else None,
                category=ExpenseCategory(category) if category else None,
                merchant=payload.get("merchant"),
                payer_id=payload.get("payer_id"),
            )
            return {
                "phase": "collecting",
                "response": f"Expense {expense_id} confirmed.",
                "expense": expense_to_api(expense, session),
            }

        if action == "assign_split":
            expense = self._ledger.assign_split(
                session,
                payload["expense_id"],
                payload.get("member_ids") or payload.get("split_among"),
                payer_id=payload.get("payer_id"),
            )
            return {
                "phase": "collecting",
                "response": f"Split updated for expense {expense.expense_id}.",
                "expense": expense_to_api(expense, session),
            }

        if action == "list_expenses":
            return {
                "phase": session.status.value,
                "expenses": [expense_to_api(e, session) for e in session.expenses],
                "response": f"{len(session.expenses)} expense(s) recorded.",
            }

        if action == "list_members":
            members = [m.model_dump() for m in session.members.values()]
            return {
                "phase": session.status.value,
                "members": members,
                "response": f"{len(members)} member(s) registered.",
            }

        if action == "list_balances":
            balances = self._ledger.compute_balances(session)
            return {
                "phase": session.status.value,
                "balances": {k: v.model_dump() for k, v in balances.items()},
                "response": "Current balances computed.",
            }

        if action == "confirm_bills":
            self._ledger.confirm_bills(session)
            return {
                "phase": session.status.value,
                "response": (
                    f"Confirmed {len(session.confirmed_expenses())} bill(s) — ready to settle."
                ),
                "expense_count": len(session.confirmed_expenses()),
            }

        if action == "finalize":
            include_b64 = payload.get("format") == "base64"
            missing = self._ledger.missing_for_finalize(session)
            if missing:
                raise ValueError(f"Cannot finalize: {', '.join(missing)}")
            result = self._settlement.finalize(session, include_base64=include_b64)
            session.status = SessionStatus.SETTLED
            session.settlement_result = result.model_dump(mode="json")
            return {
                "phase": "settled",
                "response": result.summary,
                "balances": {k: v.model_dump() for k, v in result.balances.items()},
                "transfers": [t.model_dump() for t in result.transfers],
                "summary": result.summary,
            }

        if action == "get_settlement":
            if session.status != SessionStatus.SETTLED or not session.settlement_result:
                raise ValueError("Session not settled yet — call finalize first")
            return {
                "phase": "settled",
                "response": session.settlement_result.get("summary", ""),
                **session.settlement_result,
            }

        raise ValueError(f"Unknown action: {action}")
