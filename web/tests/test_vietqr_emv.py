"""Unit tests for local VietQR EMV generation."""

from __future__ import annotations

import unittest

from web.vietqr_emv import (
    build_emv_payload,
    build_vietqr_image,
    crc16_ccitt_false,
    should_render_locally,
)


class VietQREmvTests(unittest.TestCase):
    def test_crc16_known_vector(self) -> None:
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_acb_dynamic_fixture(self) -> None:
        payload = build_emv_payload(
            bank_bin="970416",
            account_no="257678859",
            amount_vnd=1000,
            transfer_content="Chuyen tien",
        )
        self.assertTrue(payload.startswith("000201010212"))
        self.assertIn("970416", payload)
        self.assertIn("257678859", payload)
        self.assertIn("54041000", payload)
        without_crc = payload[:-4]
        expected_crc = f"{crc16_ccitt_false(without_crc.encode('ascii')):04X}"
        self.assertEqual(payload[-4:], expected_crc)

    def test_zalopay_bin_local_only(self) -> None:
        self.assertTrue(should_render_locally("971101"))

    def test_zalopay_payload_and_image(self) -> None:
        result = build_vietqr_image(
            bank_bin="971101",
            account_no="0901234567",
            account_name="0901234567",
            amount_vnd=500_000,
            transfer_content="Trip thu quy",
        )
        self.assertTrue(result.payload.startswith("000201"))
        self.assertIn("971101", result.payload)
        self.assertIn("0901234567", result.payload)
        self.assertTrue(result.payload.endswith(result.payload[-4:].upper()))
        self.assertTrue(len(result.png_base64) > 100)
        self.assertTrue(result.data_url.startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
