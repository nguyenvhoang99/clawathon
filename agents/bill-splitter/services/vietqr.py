from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

import httpx


def _strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9 ]+", "", ascii_text).upper().strip()


def sanitize_transfer_content(text: str, max_len: int = 25) -> str:
    clean = _strip_diacritics(text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_len] if clean else "Trip settle"


def build_vietqr_url(
    bank_bin: str,
    account_no: str,
    account_name: str,
    amount_vnd: int,
    transfer_content: str,
    template: str = "compact2",
) -> str:
    bin_id = bank_bin.strip()
    acct = account_no.strip()
    name = _strip_diacritics(account_name)
    add_info = sanitize_transfer_content(transfer_content)
    base = f"https://img.vietqr.io/image/{bin_id}-{acct}-{template}.png"
    return f"{base}?amount={amount_vnd}&addInfo={quote(add_info)}&accountName={quote(name)}"


def fetch_vietqr_base64(url: str) -> str | None:
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url)
            response.raise_for_status()
            import base64

            return base64.b64encode(response.content).decode("ascii")
    except httpx.HTTPError:
        return None
