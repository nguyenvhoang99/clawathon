from __future__ import annotations

import base64
import io
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from agents.receipt_vision import apply_form_overrides, draft_to_expense
from models.expense import ExpenseCategory, ExpenseDraft, ExpenseStatus
from models.member import MemberProfile
from models.session import BillSession, SessionStatus
from services.ledger import ExpenseLedger
from services.receipt_images import make_thumbnail_base64
from services.router import ActionRouter, expense_to_api


def _tiny_png_b64() -> str:
    img = Image.new("RGB", (8, 8), color=(200, 100, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


class ThumbnailTests(unittest.TestCase):
    def test_make_thumbnail_base64(self) -> None:
        raw = base64.b64decode(_tiny_png_b64())
        thumb = make_thumbnail_base64(raw)
        self.assertTrue(len(thumb) > 20)
        decoded = base64.b64decode(thumb)
        img = Image.open(io.BytesIO(decoded))
        self.assertLessEqual(max(img.size), 200)


class FormOverrideTests(unittest.TestCase):
    def test_apply_form_overrides(self) -> None:
        draft = ExpenseDraft(merchant="Old", total_vnd=1000, category=ExpenseCategory.OTHER)
        updated = apply_form_overrides(
            draft,
            {"merchant": "Cafe", "total_vnd": 50000, "category": "food", "notes": "Lunch"},
        )
        self.assertEqual(updated.merchant, "Cafe")
        self.assertEqual(updated.total_vnd, 50000)
        self.assertEqual(updated.category, ExpenseCategory.FOOD)
        self.assertEqual(updated.notes, "Lunch")


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ExpenseLedger()
        self.session = BillSession(team_id="t1", session_id="s1")
        self.ledger.register_member(
            self.session,
            MemberProfile(
                member_id="alice",
                display_name="Alice",
                bank_bin="970422",
                account_no="0901234567",
                account_name="ALICE",
            ),
        )
        self.ledger.register_member(
            self.session,
            MemberProfile(
                member_id="bob",
                display_name="Bob",
                bank_bin="970422",
                account_no="0902345678",
                account_name="BOB",
            ),
        )

    def test_duplicate_receipt_rejected(self) -> None:
        draft = ExpenseDraft(merchant="Shop", total_vnd=100000, confidence=1.0)
        expense = draft_to_expense(
            draft,
            self.session,
            "alice",
            "hash123",
            ["alice", "bob"],
            receipt_thumbnail_base64="abc",
            force_confirm=True,
        )
        self.ledger.add_expense(self.session, expense)
        with self.assertRaises(ValueError):
            self.ledger.assert_no_duplicate_receipt(self.session, "hash123")

    def test_list_balances_include_account_no(self) -> None:
        self.ledger.add_manual_expense(
            self.session,
            uploaded_by="alice",
            payer_id="alice",
            total_vnd=200000,
            category=ExpenseCategory.FOOD,
            split_among=["alice", "bob"],
            merchant="BBQ",
        )
        balances = self.ledger.compute_balances(self.session)
        self.assertEqual(balances["alice"].account_no, "0901234567")
        self.assertEqual(balances["bob"].display_name, "Bob")

    def test_confirm_bills_sets_ready(self) -> None:
        self.ledger.add_manual_expense(
            self.session,
            uploaded_by="alice",
            payer_id="alice",
            total_vnd=200000,
            category=ExpenseCategory.FOOD,
            split_among=["alice", "bob"],
            merchant="BBQ",
        )
        self.ledger.confirm_bills(self.session)
        self.assertEqual(self.session.status, SessionStatus.READY_TO_SETTLE)

    def test_confirm_bills_rejects_drafts(self) -> None:
        draft = ExpenseDraft(merchant="Shop", total_vnd=100000, confidence=0.5)
        expense = draft_to_expense(draft, self.session, "alice", "hash456", ["alice", "bob"])
        self.ledger.add_expense(self.session, expense)
        with self.assertRaises(ValueError):
            self.ledger.confirm_bills(self.session)


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = ActionRouter(MagicMock(), MagicMock())

    @patch("services.router.load_session")
    @patch("services.router.save_session")
    def test_list_members(self, _save: MagicMock, load: MagicMock) -> None:
        session = BillSession(team_id="t1", session_id="s1")
        session.members["alice"] = MemberProfile(
            member_id="alice",
            display_name="Alice",
            account_no="0901234567",
        )
        load.return_value = session
        result = self.router.handle(
            {"action": "list_members"},
            team_id="t1",
            session_id="s1",
            user_id="alice",
        )
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["members"]), 1)
        self.assertEqual(result["members"][0]["display_name"], "Alice")

    @patch("services.router.load_session")
    @patch("services.router.save_session")
    @patch("services.router.extract_receipt")
    def test_upload_receipt_with_form_overrides(
        self,
        extract: MagicMock,
        _save: MagicMock,
        load: MagicMock,
    ) -> None:
        session = BillSession(team_id="t1", session_id="s1")
        session.members["alice"] = MemberProfile(
            member_id="alice",
            display_name="Alice",
            bank_bin="970422",
            account_no="0901234567",
            account_name="ALICE",
        )
        load.return_value = session
        extract.return_value = ExpenseDraft(
            merchant="OCR Shop",
            total_vnd=999,
            category=ExpenseCategory.OTHER,
            confidence=0.4,
        )
        png_b64 = _tiny_png_b64()
        result = self.router.handle(
            {
                "action": "upload_receipt",
                "image_base64": png_b64,
                "image_media_type": "image/png",
                "payer_id": "alice",
                "merchant": "Form Shop",
                "total_vnd": 120000,
                "category": "food",
                "member_ids": ["alice"],
            },
            team_id="t1",
            session_id="s1",
            user_id="alice",
        )
        self.assertEqual(result["status"], "success")
        expense = result["expense"]
        self.assertEqual(expense["merchant"], "Form Shop")
        self.assertEqual(expense["total_vnd"], 120000)
        self.assertEqual(expense["category"], "food")
        self.assertEqual(expense["payer_display_name"], "Alice")
        self.assertTrue(expense["has_receipt"])
        self.assertTrue(expense["receipt_thumbnail_base64"])

    def test_expense_to_api(self) -> None:
        session = BillSession(team_id="t1", session_id="s1")
        session.members["alice"] = MemberProfile(member_id="alice", display_name="Alice")
        draft = ExpenseDraft(merchant="Cafe", total_vnd=50000, confidence=1.0)
        expense = draft_to_expense(
            draft,
            session,
            "alice",
            "h1",
            ["alice"],
            receipt_thumbnail_base64="thumb",
            force_confirm=True,
        )
        api = expense_to_api(expense, session)
        self.assertEqual(api["payer_display_name"], "Alice")
        self.assertTrue(api["has_receipt"])
        self.assertEqual(expense.status, ExpenseStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
