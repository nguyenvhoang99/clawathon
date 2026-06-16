#!/usr/bin/env python3
"""Post-deploy API verification for trip-web-proxy and backing agents.

Usage:
  BASE_URL=https://endpoint-....agentbase-runtime.../ python3 -m unittest web.tests.test_deploy_api
  API_TEST_MODE=full BASE_URL=... python3 web/tests/test_deploy_api.py

Environment:
  BASE_URL          Proxy or web runtime URL (default http://127.0.0.1:8080)
  TEAM_ID           X-GreenNode-AgentBase-Custom-Team-Id (default team-api-test)
  SESSION_ID        Session header (default session-api-<pid>)
  API_TEST_MODE     smoke | full (default smoke)
  API_TEST_TIMEOUT  Per-request timeout seconds (default 120)
  ZALOPAY_BIN       NAPAS bin for bill member registration (fallback 971101)
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import unittest
from datetime import date
from pathlib import Path

# Allow running as script: python3 web/tests/test_deploy_api.py
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "web.tests"

from web.tests.api_client import ApiClient, client_from_env, read_zalopay_bank_bin


def _mode() -> str:
    return os.environ.get("API_TEST_MODE", "smoke").strip().lower()


def _is_full() -> bool:
    return _mode() == "full"


def _tiny_png_b64() -> str:
    try:
        from PIL import Image  # type: ignore[import-untyped]

        buf = io.BytesIO()
        Image.new("RGB", (16, 16), color=(0, 180, 100)).save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        return (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )


class DeployApiSmokeTests(unittest.TestCase):
    """Fast checks suitable after every deploy (~30s)."""

    client: ApiClient
    bank_bin: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = client_from_env()
        cls.bank_bin = read_zalopay_bank_bin()
        cls.current_year = date.today().year

    def test_01_health(self) -> None:
        status, body = self.client.get("/health")
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("status"), "ok")

    def test_02_estimates(self) -> None:
        status, body = self.client.post(
            "/api/estimates",
            {
                "trip_brief": {
                    "origin_city": "Ho Chi Minh City",
                    "destination_city": "Da Nang",
                    "start_date": f"{self.current_year}-03-20",
                    "headcount": 10,
                },
                "budget_ledger": {},
            },
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("originCode"), "SGN")
        self.assertEqual(body.get("destCode"), "DAD")
        categories = body.get("categories") or []
        self.assertGreaterEqual(len(categories), 4, "expected flight/train/bus/hotel categories")
        ids = {c.get("id") for c in categories}
        self.assertIn("flight", ids)
        self.assertIn("hotel", ids)

    def test_03_weather(self) -> None:
        status, body = self.client.post(
            "/api/weather",
            {"message": "What is the weather in Hanoi today?"},
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("status"), "success")
        response = (body.get("response") or "").strip()
        self.assertTrue(len(response) > 10, "weather response should not be empty")

    def test_04_trip_intake_missing_origin(self) -> None:
        status, body = self.client.post(
            "/api/trip",
            {"message": "10 người đi Đà Nẵng 20-23/3, 5 triệu/người"},
        )
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("status"), "success")
        self.assertEqual(body.get("phase"), "intake")
        self.assertEqual(body.get("intake_field"), "origin_city")
        self.assertTrue(body.get("location_prompt"))

        brief = body.get("trip_brief") or {}
        self.assertEqual(brief.get("destination_city"), "Da Nang")
        start = brief.get("start_date") or ""
        self.assertTrue(start.startswith(f"{self.current_year}-"), f"start_date should use {self.current_year}: {start}")

    def test_05_bill_list_balances(self) -> None:
        status, body = self.client.post("/api/bill", {"action": "list_balances"})
        self.assertEqual(status, 200, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("status"), "success")
        self.assertIn("balances", body)

    def test_06_bill_link_trip(self) -> None:
        status, body = self.client.post(
            "/api/bill",
            {
                "action": "link_trip",
                "trip_id": f"{self.client.team_id}:{self.client.session_id}",
                "contribution_vnd_per_member": 2_500_000,
            },
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body.get("status"), "success")


@unittest.skipUnless(_is_full(), "full mode only (API_TEST_MODE=full)")
class DeployApiFullTests(unittest.TestCase):
    """Slower end-to-end flows (~2–3 min). Run before major releases."""

    client: ApiClient
    bank_bin: str
    members = (
        ("alice", "Alice", "0901234567"),
        ("bob", "Bob", "0902345678"),
        ("charlie", "Charlie", "0903456789"),
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = client_from_env()
        cls.client.timeout_sec = max(cls.client.timeout_sec, 180)
        cls.bank_bin = read_zalopay_bank_bin()

    def test_10_trip_full_plan(self) -> None:
        status, body = self.client.post(
            "/api/trip",
            {
                "message": (
                    "10 people from Ho Chi Minh City to Da Nang 20-23/3, "
                    "5 million VND per person, beach and food"
                )
            },
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body.get("status"), "success")
        self.assertEqual(body.get("phase"), "done", body.get("response"))
        brief = body.get("trip_brief") or {}
        self.assertEqual(brief.get("origin_city"), "Ho Chi Minh City")
        self.assertEqual(brief.get("destination_city"), "Da Nang")
        self.assertTrue(body.get("response"), "plan response text missing")
        self.assertTrue(body.get("budget_ledger") or body.get("plan"), "expected budget or plan payload")

    def test_11_bill_register_members(self) -> None:
        for member_id, name, phone in self.members:
            status, body = self.client.post(
                "/api/bill",
                {
                    "action": "register_member",
                    "member_id": member_id,
                    "display_name": name,
                    "bank_bin": self.bank_bin,
                    "bank_code": "ZLP",
                    "account_no": phone,
                    "account_name": name.upper(),
                },
                user_id=member_id,
            )
            self.assertEqual(status, 200, body)
            self.assertEqual(body.get("status"), "success")

        status, body = self.client.post(
            "/api/bill",
            {"action": "list_members"},
            user_id="alice",
        )
        self.assertEqual(status, 200, body)
        self.assertGreaterEqual(len(body.get("members") or []), 3)

    def test_12_bill_upload_receipt(self) -> None:
        status, body = self.client.post(
            "/api/bill",
            {
                "action": "upload_receipt",
                "image_base64": _tiny_png_b64(),
                "image_media_type": "image/png",
                "payer_id": "alice",
                "merchant": "API test receipt",
                "total_vnd": 150_000,
                "category": "food",
                "member_ids": ["alice", "bob", "charlie"],
                "notes": "deploy api test",
            },
            user_id="alice",
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(body.get("status"), "success")

    def test_13_bill_add_expenses_and_balances(self) -> None:
        for payload in (
            {
                "action": "add_expense",
                "total_vnd": 900_000,
                "category": "food",
                "merchant": "Seafood BBQ",
                "payer_id": "alice",
                "member_ids": ["alice", "bob", "charlie"],
            },
            {
                "action": "add_expense",
                "total_vnd": 300_000,
                "category": "transport",
                "merchant": "Grab",
                "payer_id": "bob",
                "member_ids": ["alice", "bob", "charlie"],
            },
        ):
            status, body = self.client.post("/api/bill", payload, user_id=payload["payer_id"])
            self.assertEqual(status, 200, body)

        status, body = self.client.post(
            "/api/bill",
            {"action": "list_expenses"},
            user_id="alice",
        )
        self.assertEqual(status, 200, body)
        self.assertGreaterEqual(len(body.get("expenses") or []), 1)

        status, body = self.client.post(
            "/api/bill",
            {"action": "list_balances"},
            user_id="alice",
        )
        self.assertEqual(status, 200, body)
        alice = (body.get("balances") or {}).get("alice") or {}
        self.assertIsNotNone(alice.get("account_no"))

    def test_14_bill_finalize_settlement(self) -> None:
        status, body = self.client.post(
            "/api/bill",
            {"action": "confirm_bills"},
            user_id="alice",
        )
        self.assertEqual(status, 200, body)

        status, body = self.client.post(
            "/api/bill",
            {"action": "finalize"},
            user_id="alice",
        )
        self.assertEqual(status, 200, body)
        payload = json.dumps(body) if isinstance(body, dict) else str(body)
        self.assertIn("vietqr", payload.lower(), "finalize should return VietQR URLs")


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = loader.loadTestsFromTestCase(DeployApiSmokeTests)
    if _is_full():
        suite.addTests(loader.loadTestsFromTestCase(DeployApiFullTests))
    return suite


if __name__ == "__main__":
    print(f"BASE_URL={client_from_env().base_url}  mode={_mode()}")
    unittest.main(verbosity=2)
