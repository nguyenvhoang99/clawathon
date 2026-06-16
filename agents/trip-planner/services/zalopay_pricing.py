"""Look up Zalopay weekly mock prices and build the 4 spending categories.

The mockdata in `data/zalopay_*_est_price.json` is grouped by ISO week
(`week` = "YYYY-WNN", `week_start` = the Monday of that week). When the trip
start_date is known we filter to that week first; otherwise we fall back to
the nearest week, and finally to any week.

Each of the 4 categories (flight, train, bus, hotel) returns up to 4 options:
- 1 Zalopay option (from mockdata) if a route/city + week match is found,
  otherwise a QR slot pointing to the Zalopay app
- Up to 3 brand fallbacks with prices ≤300K VND gap
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CITY_CODES = {
    "ho chi minh city": "SGN",
    "hcmc": "SGN",
    "saigon": "SGN",
    "tp hcm": "SGN",
    "tp.hcm": "SGN",
    "hanoi": "HAN",
    "ha noi": "HAN",
    "da nang": "DAD",
    "danang": "DAD",
    "phu quoc": "PQC",
    "nha trang": "NHA",
    "hue": "HUI",
    "hoi an": "DAD",
    "can tho": "CTO",
    "vung tau": "VTU",
    "buon ma thuot": "BMT",
    "da lat": "DLI",
    "quy nhon": "UIH",
    "vinh": "VII",
    "hai phong": "HPH",
}

BRAND_FALLBACKS = {
    "flight": [
        {"provider": "Vietjet Air", "type": "Máy bay", "url": "https://www.vietjetair.com/vi/"},
        {"provider": "Bamboo Airways", "type": "Máy bay", "url": "https://www.bambooairways.com/vi/"},
        {"provider": "Vietnam Airlines", "type": "Máy bay", "url": "https://www.vietnamairlines.com/vn/vi/home"},
    ],
    "train": [
        {"provider": "Đường sắt Việt Nam", "type": "Tàu hỏa", "url": "https://dsvn.vn/"},
        {"provider": "Vexere", "type": "Tàu hỏa", "url": "https://vexere.com/vi-VN/"},
        {"provider": "12go Asia", "type": "Tàu hỏa", "url": "https://12go.asia/vi"},
    ],
    "bus": [
        {"provider": "Phương Trang FUTA", "type": "Xe khách", "url": "https://futabus.vn/"},
        {"provider": "Hoàng Long", "type": "Xe khách", "url": "https://hoanglong.vn/"},
        {"provider": "Sao Việt", "type": "Xe khách", "url": "https://saoviet.com.vn/"},
    ],
    "hotel": [
        {"provider": "Booking.com", "type": "Khách sạn", "url": "https://www.booking.com/"},
        {"provider": "Agoda", "type": "Khách sạn", "url": "https://www.agoda.com/vi-vn/"},
        {"provider": "Traveloka", "type": "Khách sạn", "url": "https://www.traveloka.com/vi-vn/hotel/"},
    ],
}

MAX_PRICE_GAP = 300_000

FLIGHT_BRAND_BASE = {
    "Vietjet Air": 1_400_000,
    "Bamboo Airways": 1_800_000,
    "Vietnam Airlines": 2_400_000,
}
HOTEL_BRAND_BASE = {
    "Booking.com": 900_000,
    "Agoda": 750_000,
    "Traveloka": 850_000,
}
TRAIN_BRAND_BASE = {
    "Đường sắt Việt Nam": 700_000,
    "Vexere": 650_000,
    "12go Asia": 750_000,
}
BUS_BRAND_BASE = {
    "Phương Trang FUTA": 400_000,
    "Hoàng Long": 450_000,
    "Sao Việt": 420_000,
}


def normalize_city(city: str) -> str:
    text = unicodedata.normalize("NFD", (city or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("tp.", "tp ").replace("-", " ")
    return " ".join(text.split())


def city_to_code(city: str) -> str | None:
    key = normalize_city(city)
    if key in CITY_CODES:
        return CITY_CODES[key]
    for alias, code in CITY_CODES.items():
        if alias in key or key in alias:
            return code
    return None


def iso_week_label(start_date: str | date | None) -> str | None:
    if not start_date:
        return None
    if isinstance(start_date, str):
        try:
            start_date = date.fromisoformat(start_date[:10])
        except ValueError:
            return None
    if not isinstance(start_date, date):
        return None
    iso_year, iso_week, _ = start_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _week_distance(week_label: str, target: str) -> int:
    """Absolute distance in weeks between two ISO week labels."""
    try:
        ty, tw = target.split("-W")
        ly, lw = week_label.split("-W")
        return abs((int(ly) - int(ty)) * 52 + (int(lw) - int(tw)))
    except (ValueError, AttributeError):
        return 9999


@lru_cache(maxsize=8)
def _load_json(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _round_hundreds(value: int | float | None) -> int:
    if value is None:
        return 0
    return max(0, int(round(float(value) / 100) * 100))


def _clamp_range(price_min: int, price_max: int) -> tuple[int, int]:
    price_min = _round_hundreds(price_min)
    price_max = _round_hundreds(price_max)
    if price_max < price_min:
        price_max = price_min
    if price_max - price_min > MAX_PRICE_GAP:
        price_max = price_min + MAX_PRICE_GAP
    return price_min, price_max


def _mid_range(mid: int, spread: int = 150_000) -> tuple[int, int]:
    return _clamp_range(mid - spread, mid + spread)


def _filter_by_week(rows: list[dict], target_week: str | None) -> list[dict]:
    """Return rows from the target week, otherwise the nearest week, otherwise all rows."""
    if not rows:
        return rows
    if not target_week:
        return rows
    exact = [r for r in rows if r.get("week") == target_week]
    if exact:
        return exact
    rows_sorted = sorted(
        rows,
        key=lambda r: _week_distance(r.get("week", ""), target_week),
    )
    nearest_distance = _week_distance(rows_sorted[0].get("week", ""), target_week)
    if nearest_distance > 12:
        return rows
    nearest_week = rows_sorted[0].get("week")
    return [r for r in rows_sorted if r.get("week") == nearest_week]


def _option(
    *,
    provider: str,
    name: str,
    type_label: str,
    price_min: int,
    price_max: int,
    unit: str,
    note: str,
    is_zalopay: bool = False,
    is_qr_slot: bool = False,
    qr_image: str | None = None,
    url: str | None = None,
    week: str | None = None,
) -> dict:
    price_min, price_max = _clamp_range(price_min, price_max)
    option = {
        "provider": provider,
        "name": name,
        "type": type_label,
        "priceMin": price_min,
        "priceMax": price_max,
        "unit": unit,
        "note": note,
        "isZalopay": is_zalopay,
        "url": url,
    }
    if week:
        option["week"] = week
    if is_qr_slot:
        option["isQrSlot"] = True
        option["qrImage"] = qr_image
    return option


def _qr_path(category: str) -> str | None:
    for ext in (".jpg", ".JPG"):
        candidate = DATA_DIR / f"zalopay_{category}_qr_link{ext}"
        if candidate.exists():
            return f"/data/qr/{candidate.name}"
    return None


def _zalopay_qr_option(category_id: str, type_label: str) -> dict | None:
    qr = _qr_path(category_id)
    if not qr:
        return None
    return _option(
        provider="Zalopay",
        name="Quét mã trên app",
        type_label=type_label,
        price_min=0,
        price_max=0,
        unit="",
        note="Tìm thêm giá trên Zalopay",
        is_zalopay=True,
        is_qr_slot=True,
        qr_image=qr,
    )


def _pick_flight(origin: str, dest: str, target_week: str | None) -> dict | None:
    data = _load_json("zalopay_flight_est_price.json")
    rows = [
        e
        for e in (data.get("estimates") or [])
        if e.get("departure_airport") == origin and e.get("arrival_airport") == dest
    ]
    rows = _filter_by_week(rows, target_week)
    if not rows:
        return None
    economy = [e for e in rows if "economy" in (e.get("fare_class") or "").lower()]
    pool = economy or rows
    pool.sort(key=lambda e: _round_hundreds(e.get("est_total_price_vnd")))
    best = pool[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('airline_name', 'Bay nội địa')} · {best.get('fare_class', 'Economy')}",
        type_label="Máy bay",
        price_min=_round_hundreds(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_round_hundreds(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/khứ hồi",
        note=f"{origin} → {dest} · Zalopay tuần {best.get('week', '?')}",
        is_zalopay=True,
        week=best.get("week"),
    )


def _pick_train(origin: str, dest: str, target_week: str | None) -> dict | None:
    data = _load_json("zalopay_train_est_price.json")
    rows = [
        e
        for e in (data.get("estimates") or [])
        if e.get("from_code") == origin and e.get("to_code") == dest
    ]
    rows = _filter_by_week(rows, target_week)
    if not rows:
        return None
    rows.sort(key=lambda e: _round_hundreds(e.get("est_total_price_vnd")))
    best = rows[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('train_name', 'Tàu')} · {best.get('seat_type_label', 'Ghế ngồi')}",
        type_label="Tàu hỏa",
        price_min=_round_hundreds(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_round_hundreds(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/người",
        note=f"{best.get('from_name', origin)} → {best.get('to_name', dest)} · tuần {best.get('week', '?')}",
        is_zalopay=True,
        week=best.get("week"),
    )


def _pick_bus(origin: str, dest: str, target_week: str | None) -> dict | None:
    data = _load_json("zalopay_bus_est_price.json")
    rows = [
        e
        for e in (data.get("estimates") or [])
        if e.get("from_code") == origin and e.get("to_code") == dest
    ]
    rows = _filter_by_week(rows, target_week)
    if not rows:
        return None
    rows.sort(key=lambda e: _round_hundreds(e.get("est_total_price_vnd")))
    best = rows[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('operator_name', 'Xe khách')} · {best.get('seat_type', 'Ghế')}",
        type_label="Xe khách",
        price_min=_round_hundreds(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_round_hundreds(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/người",
        note=f"{best.get('from_name', origin)} → {best.get('to_name', dest)} · tuần {best.get('week', '?')}",
        is_zalopay=True,
        week=best.get("week"),
    )


def _pick_hotel(dest: str, target_week: str | None) -> dict | None:
    data = _load_json("zalopay_hotel_est_price.json")
    rows = [e for e in (data.get("estimates") or []) if e.get("hotel_city_code") == dest]
    rows = _filter_by_week(rows, target_week)
    if not rows:
        return None
    by_hotel: dict[str, dict] = {}
    for row in rows:
        hid = row.get("hotel_id") or row.get("hotel_name")
        existing = by_hotel.get(hid)
        if existing is None or _round_hundreds(row.get("est_total_price_vnd")) < _round_hundreds(
            existing.get("est_total_price_vnd")
        ):
            by_hotel[hid] = row
    best = min(by_hotel.values(), key=lambda e: _round_hundreds(e.get("est_total_price_vnd")))
    return _option(
        provider="Zalopay",
        name=f"{best.get('hotel_name', 'Khách sạn')} · {best.get('room_type', 'Standard')}",
        type_label="Lưu trú",
        price_min=_round_hundreds(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_round_hundreds(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/đêm",
        note=f"{best.get('breakfast_option') or best.get('hotel_city') or dest} · tuần {best.get('week', '?')}",
        is_zalopay=True,
        week=best.get("week"),
    )


def _brand_options(category: str) -> list[dict]:
    base_map = {
        "flight": FLIGHT_BRAND_BASE,
        "hotel": HOTEL_BRAND_BASE,
        "train": TRAIN_BRAND_BASE,
        "bus": BUS_BRAND_BASE,
    }[category]
    options = []
    for brand in BRAND_FALLBACKS.get(category, []):
        mid = base_map.get(brand["provider"], 500_000)
        price_min, price_max = _mid_range(mid)
        unit_map = {"flight": "/khứ hồi", "hotel": "/đêm", "train": "/người", "bus": "/người"}
        options.append(
            _option(
                provider=brand["provider"],
                name=brand["provider"],
                type_label=brand["type"],
                price_min=price_min,
                price_max=price_max,
                unit=unit_map.get(category, "/người"),
                note="",
                url=brand.get("url"),
            )
        )
    return options


def _category(
    category_id: str,
    title: str,
    type_label: str,
    zalopay_option: dict | None,
) -> dict:
    brands = _brand_options(category_id)
    if zalopay_option:
        options = [zalopay_option] + brands[:3]
    else:
        qr = _zalopay_qr_option(category_id, type_label)
        options = brands[:3] + ([qr] if qr else [])
    return {
        "id": category_id,
        "title": title,
        "options": options[:4],
        "hasZalopayMatch": bool(zalopay_option),
    }


def build_spending(trip_brief: dict) -> dict:
    """Build the 4 spending categories with weekly Zalopay lookup."""
    origin_name = trip_brief.get("origin_city") or ""
    dest_name = trip_brief.get("destination_city") or ""
    origin = city_to_code(origin_name)
    dest = city_to_code(dest_name)
    start_date = trip_brief.get("start_date")
    target_week = iso_week_label(start_date)

    categories: list[dict] = []
    if origin and dest:
        categories.append(_category("flight", "✈️ Máy bay", "Máy bay", _pick_flight(origin, dest, target_week)))
        categories.append(_category("train", "🚆 Tàu hỏa", "Tàu hỏa", _pick_train(origin, dest, target_week)))
        categories.append(_category("bus", "🚌 Xe khách", "Xe khách", _pick_bus(origin, dest, target_week)))
    else:
        categories.append(_category("flight", "✈️ Máy bay", "Máy bay", None))
        categories.append(_category("train", "🚆 Tàu hỏa", "Tàu hỏa", None))
        categories.append(_category("bus", "🚌 Xe khách", "Xe khách", None))
    categories.append(_category("hotel", "🏨 Lưu trú", "Lưu trú", _pick_hotel(dest, target_week) if dest else None))

    return {
        "originCode": origin,
        "destCode": dest,
        "week": target_week,
        "categories": categories,
    }
