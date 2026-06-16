from __future__ import annotations

import re
from datetime import date


def resolve_year_month(year: int | None, month: int | None) -> tuple[int, int]:
    today = date.today()
    return year or today.year, month or today.month


def year_explicit_in_text(message: str) -> bool:
    return bool(re.search(r"\b20\d{2}\b", message))


def coerce_dates_to_current_year_if_omitted(message: str, start: date | None, end: date | None) -> tuple[date | None, date | None]:
    """When the user omits a year, force dates to the current calendar year."""
    if year_explicit_in_text(message) or (not start and not end):
        return start, end
    today = date.today()
    if start:
        start = start.replace(year=today.year)
    if end:
        end = end.replace(year=today.year)
    return start, end


def parse_dates_from_text(message: str) -> dict:
    """Parse trip dates; default missing month/year to current month/year."""
    lower = message.lower()
    today = date.today()

    match = re.search(
        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?",
        lower,
    )
    if match:
        start_day = int(match.group(1))
        end_day = int(match.group(2))
        month = int(match.group(3))
        year = int(match.group(4)) if match.group(4) else None
        year, month = resolve_year_month(year, month)
        return {
            "start_date": date(year, month, start_day),
            "end_date": date(year, month, end_day),
        }

    match = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{4}))?", lower)
    if match and "budget" not in lower[max(0, match.start() - 12) : match.start()]:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else None
        year, month = resolve_year_month(year, month)
        trip_day = date(year, month, day)
        return {"start_date": trip_day, "end_date": trip_day}

    match = re.search(
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s*[-–]\s*(\d{1,2})(?:\s*,?\s*(\d{4}))?",
        lower,
    )
    if match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months[match.group(1)[:3]]
        year = int(match.group(4)) if match.group(4) else None
        year, month = resolve_year_month(year, month)
        return {
            "start_date": date(year, month, int(match.group(2))),
            "end_date": date(year, month, int(match.group(3))),
        }

    return {}
