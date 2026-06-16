"""Build NAPAS VietQR (EMVCo) payloads and render QR images locally.

img.vietqr.io does not support every BIN (e.g. ZaloPay 971101). This module
builds the EMV TLV string per Napas 247 / EMVCo MPM v1.1 and renders PNG via
qrcode — no external VietQR API required.
"""

from __future__ import annotations

import base64
import io
import re
import unicodedata
from dataclasses import dataclass

# Bins that img.vietqr.io rejects — always render locally.
LOCAL_ONLY_BINS = frozenset({"971101"})


def tlv(tag: str, value: str) -> str:
    if len(tag) != 2:
        raise ValueError(f"TLV tag must be 2 digits, got {tag!r}")
    if not (1 <= len(value) <= 99):
        raise ValueError(f"TLV value length out of range (1-99): {len(value)}")
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9 ]+", "", ascii_text).upper().strip()


def sanitize_transfer_content(text: str, max_len: int = 25) -> str:
    clean = _strip_diacritics(text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_len] if clean else "Trip settle"


def _napas_consumer(bank_bin: str, account_no: str) -> str:
    bin_id = bank_bin.strip()
    acct = account_no.strip()
    return tlv("00", bin_id) + tlv("01", acct)


def _napas_merchant_account(bank_bin: str, account_no: str, service_code: str = "QRIBFTTA") -> str:
    return (
        tlv("00", "A000000727")
        + tlv("01", _napas_consumer(bank_bin, account_no))
        + tlv("02", service_code)
    )


def build_emv_payload(
    bank_bin: str,
    account_no: str,
    amount_vnd: int | None = None,
    transfer_content: str | None = None,
    *,
    dynamic: bool | None = None,
) -> str:
    """Return a scannable VietQR EMV string (includes CRC field 63)."""
    if dynamic is None:
        dynamic = bool(amount_vnd and amount_vnd > 0)

    parts = [
        tlv("00", "01"),
        tlv("01", "12" if dynamic else "11"),
        tlv("38", _napas_merchant_account(bank_bin, account_no)),
        tlv("53", "704"),
    ]
    if amount_vnd and amount_vnd > 0:
        parts.append(tlv("54", str(int(amount_vnd))))
    parts.append(tlv("58", "VN"))
    if transfer_content:
        purpose = sanitize_transfer_content(transfer_content)
        parts.append(tlv("62", tlv("08", purpose)))

    without_crc = "".join(parts) + "6304"
    crc = crc16_ccitt_false(without_crc.encode("ascii"))
    return without_crc + f"{crc:04X}"


def render_qr_png_base64(payload: str) -> str:
    import qrcode

    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@dataclass(frozen=True)
class VietQRImage:
    payload: str
    png_base64: str

    @property
    def data_url(self) -> str:
        return f"data:image/png;base64,{self.png_base64}"


def build_vietqr_image(
    bank_bin: str,
    account_no: str,
    account_name: str,
    amount_vnd: int,
    transfer_content: str,
) -> VietQRImage:
    """Build EMV payload and PNG QR (local generation). account_name kept for API compat."""
    _ = account_name  # EMV VietQR to-account omits merchant name; kept for callers
    payload = build_emv_payload(
        bank_bin=bank_bin,
        account_no=account_no,
        amount_vnd=amount_vnd,
        transfer_content=transfer_content,
        dynamic=True,
    )
    png_b64 = render_qr_png_base64(payload)
    return VietQRImage(payload=payload, png_base64=png_b64)


def should_render_locally(bank_bin: str) -> bool:
    return bank_bin.strip() in LOCAL_ONLY_BINS


def build_vietqr_url(
    bank_bin: str,
    account_no: str,
    account_name: str,
    amount_vnd: int,
    transfer_content: str,
    template: str = "compact2",
) -> str:
    """Return img URL for supported BINs, or a data: URL when rendered locally."""
    if should_render_locally(bank_bin):
        return build_vietqr_image(
            bank_bin, account_no, account_name, amount_vnd, transfer_content
        ).data_url

    from urllib.parse import quote

    bin_id = bank_bin.strip()
    acct = account_no.strip()
    name = _strip_diacritics(account_name)
    add_info = sanitize_transfer_content(transfer_content)
    base = f"https://img.vietqr.io/image/{bin_id}-{acct}-{template}.png"
    return f"{base}?amount={amount_vnd}&addInfo={quote(add_info)}&accountName={quote(name)}"


def fetch_vietqr_base64(url: str) -> str | None:
    if url.startswith("data:image/png;base64,"):
        return url.split(",", 1)[1]

    try:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            response = client.get(url)
            response.raise_for_status()
            return base64.b64encode(response.content).decode("ascii")
    except Exception:
        return None
