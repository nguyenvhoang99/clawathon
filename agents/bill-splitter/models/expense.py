from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ExpenseCategory(str, Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    STAY = "stay"
    ACTIVITY = "activity"
    OTHER = "other"


class ExpenseStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class LineItem(BaseModel):
    description: str
    amount_vnd: int
    quantity: int = 1


class Expense(BaseModel):
    expense_id: str
    uploaded_by: str
    payer_id: str
    merchant: str | None = None
    category: ExpenseCategory = ExpenseCategory.OTHER
    total_vnd: int
    line_items: list[LineItem] = Field(default_factory=list)
    split_among: list[str] = Field(default_factory=list)
    status: ExpenseStatus = ExpenseStatus.DRAFT
    receipt_image_hash: str | None = None
    receipt_thumbnail_base64: str | None = None
    extracted_confidence: float = 0.0
    notes: str = ""
    expense_date: str | None = None


class ExpenseDraft(BaseModel):
    merchant: str | None = None
    expense_date: str | None = None
    total_vnd: int | None = None
    currency: str = "VND"
    category: ExpenseCategory = ExpenseCategory.OTHER
    line_items: list[LineItem] = Field(default_factory=list)
    confidence: float = 0.0
    notes: str = ""
