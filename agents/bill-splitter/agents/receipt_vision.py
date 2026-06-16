from __future__ import annotations

import hashlib
import json
import re
import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from models.expense import Expense, ExpenseCategory, ExpenseDraft, ExpenseStatus, LineItem
from models.session import BillSession

MAX_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp"}

RECEIPT_PROMPT = """Extract receipt data from this image for a Vietnam team expense tracker.
Return ONLY valid JSON:
{
  "merchant": string|null,
  "expense_date": "YYYY-MM-DD"|null,
  "total_vnd": integer|null,
  "currency": "VND",
  "category": "food"|"transport"|"stay"|"activity"|"other",
  "line_items": [{"description": string, "amount_vnd": integer, "quantity": 1}],
  "confidence": 0.0-1.0,
  "notes": string
}
Use integer VND amounts without decimals. If total unclear, set total_vnd null and explain in notes."""


def validate_image(image_base64: str, media_type: str) -> bytes:
    if media_type not in ALLOWED_MEDIA:
        raise ValueError(f"Unsupported media type: {media_type}")
    import base64

    raw = base64.b64decode(image_base64, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 4MB limit")
    return raw


def image_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def extract_receipt(
    llm: ChatOpenAI,
    image_base64: str,
    media_type: str,
    hint: str = "",
) -> ExpenseDraft:
    validate_image(image_base64, media_type)
    prompt = RECEIPT_PROMPT
    if hint:
        prompt += f"\nUser hint: {hint}"

    response = llm.invoke(
        [
            SystemMessage(content="You are a receipt OCR assistant. Output JSON only."),
            HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                    },
                ]
            ),
        ]
    )
    content = response.content.strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    data = json.loads(content)
    category_raw = data.get("category", "other")
    try:
        category = ExpenseCategory(category_raw)
    except ValueError:
        category = ExpenseCategory.OTHER

    line_items = [
        LineItem(
            description=item.get("description", "item"),
            amount_vnd=int(item.get("amount_vnd", 0)),
            quantity=int(item.get("quantity", 1)),
        )
        for item in data.get("line_items", [])
        if item.get("amount_vnd")
    ]

    total = data.get("total_vnd")
    if total is None and line_items:
        total = sum(i.amount_vnd for i in line_items)

    return ExpenseDraft(
        merchant=data.get("merchant"),
        expense_date=data.get("expense_date"),
        total_vnd=int(total) if total is not None else None,
        currency=data.get("currency", "VND"),
        category=category,
        line_items=line_items,
        confidence=float(data.get("confidence", 0.5)),
        notes=data.get("notes", ""),
    )


def draft_to_expense(
    draft: ExpenseDraft,
    session: BillSession,
    uploaded_by: str,
    receipt_hash: str,
    split_among: list[str] | None = None,
    *,
    payer_id: str | None = None,
    receipt_thumbnail_base64: str | None = None,
    force_confirm: bool = False,
) -> Expense:
    if draft.total_vnd is None:
        raise ValueError("Could not determine total_vnd — use confirm_expense with total_vnd")

    auto_confirm = force_confirm or draft.confidence >= 0.85
    participants = split_among or session.member_ids() or [uploaded_by]
    resolved_payer = payer_id or uploaded_by

    return Expense(
        expense_id=str(uuid.uuid4())[:8],
        uploaded_by=uploaded_by,
        payer_id=resolved_payer,
        merchant=draft.merchant,
        category=draft.category,
        total_vnd=draft.total_vnd,
        line_items=draft.line_items,
        split_among=participants,
        status=ExpenseStatus.CONFIRMED if auto_confirm else ExpenseStatus.DRAFT,
        receipt_image_hash=receipt_hash,
        receipt_thumbnail_base64=receipt_thumbnail_base64,
        extracted_confidence=draft.confidence,
        notes=draft.notes,
        expense_date=draft.expense_date,
    )


def apply_form_overrides(draft: ExpenseDraft, payload: dict) -> ExpenseDraft:
    """Form fields from the UI override vision extraction when provided."""
    updates: dict = {}
    if payload.get("merchant"):
        updates["merchant"] = str(payload["merchant"]).strip()
    if payload.get("total_vnd") is not None:
        updates["total_vnd"] = int(payload["total_vnd"])
    if payload.get("category"):
        try:
            updates["category"] = ExpenseCategory(payload["category"])
        except ValueError:
            updates["category"] = ExpenseCategory.OTHER
    if payload.get("notes"):
        updates["notes"] = str(payload["notes"]).strip()
    if not updates:
        return draft
    return draft.model_copy(update=updates)
