"""Load Zalopay price mockdata and return web-friendly estimate options."""

from __future__ import annotations

import json
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path


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
    try:
        ty, tw = target.split("-W")
        ly, lw = week_label.split("-W")
        return abs((int(ly) - int(ty)) * 52 + (int(lw) - int(tw)))
    except (ValueError, AttributeError):
        return 9999


def _filter_by_week(rows: list[dict], target_week: str | None) -> list[dict]:
    if not rows or not target_week:
        return rows
    exact = [r for r in rows if r.get("week") == target_week]
    if exact:
        return exact
    rows_sorted = sorted(rows, key=lambda r: _week_distance(r.get("week", ""), target_week))
    if _week_distance(rows_sorted[0].get("week", ""), target_week) > 12:
        return rows
    nearest_week = rows_sorted[0].get("week")
    return [r for r in rows_sorted if r.get("week") == nearest_week]

DATA_DIR = Path(__file__).resolve().parent / "data"
AGENT_DATA_DIR = Path(__file__).resolve().parent.parent / "agents/trip-planner/data"
QR_DIR = DATA_DIR / "qr"
AGENT_QR_DIR = AGENT_DATA_DIR


def _resolve_data_file(name: str) -> Path:
    for base in (DATA_DIR, AGENT_DATA_DIR):
        path = base / name
        if path.exists():
            return path
    return DATA_DIR / name


def _resolve_qr_file(category: str) -> Path | None:
    for ext in (".jpg", ".JPG"):
        filename = f"zalopay_{category}_qr_link{ext}"
        for base in (QR_DIR, AGENT_QR_DIR):
            path = base / filename
            if path.exists():
                return path
    return None

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
    "local": [
        {"provider": "Grab", "type": "Di chuyển", "url": "https://www.grab.com/vn/", "priceMin": 25000, "priceMax": 120000, "unit": "/chuyến", "note": "Xe máy / ô tô nội thành"},
        {"provider": "Klook", "type": "Thuê xe máy", "url": "https://www.klook.com/vi/", "priceMin": 100000, "priceMax": 200000, "unit": "/ngày", "note": "Thuê xe tại điểm đến"},
    ],
    "activity": [
        {"provider": "Klook", "type": "Vui chơi", "url": "https://www.klook.com/vi/", "priceMin": 200000, "priceMax": 500000, "unit": "/người", "note": "Tour & vé tham quan"},
        {"provider": "Tripadvisor", "type": "Tham quan", "url": "https://www.tripadvisor.com.vn/", "priceMin": 0, "priceMax": 300000, "unit": "/người", "note": "Địa điểm & review"},
    ],
}

MAX_PRICE_GAP = 300_000

FLIGHT_BRAND_MID = {
    "Vietjet Air": lambda band: (band["low"] + band["mid"]) // 2,
    "Bamboo Airways": lambda band: band["mid"],
    "Vietnam Airlines": lambda band: (band["mid"] + band["high"]) // 2,
}

HOTEL_BRAND_MID = {
    "Booking.com": 900_000,
    "Agoda": 750_000,
    "Traveloka": 850_000,
}

TRAIN_BRAND_OFFSET = {
    "Đường sắt Việt Nam": 0,
    "Vexere": -50_000,
    "12go Asia": 50_000,
}

BUS_BRAND_MID = {
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


@lru_cache(maxsize=8)
def _load_json(name: str) -> dict:
    path = _resolve_data_file(name)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _round_hundreds(value: int | float | None) -> int:
    if value is None:
        return 0
    return max(0, int(round(float(value) / 100) * 100))


def _clamp_price_range(price_min: int, price_max: int, max_gap: int = MAX_PRICE_GAP) -> tuple[int, int]:
    price_min = _round_hundreds(price_min)
    price_max = _round_hundreds(price_max)
    if price_max < price_min:
        price_max = price_min
    if price_max - price_min > max_gap:
        price_max = price_min + max_gap
    return price_min, price_max


def _mid_range(mid: int, spread: int = 150_000) -> tuple[int, int]:
    return _clamp_price_range(mid - spread, mid + spread)


def _safe_price(value: int | float | None) -> int:
    return _round_hundreds(value)


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
) -> dict:
    price_min, price_max = _clamp_price_range(price_min, price_max)
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
    if is_qr_slot:
        option["isQrSlot"] = True
        option["qrImage"] = qr_image
    return option


def _qr_path(category: str) -> str | None:
    path = _resolve_qr_file(category)
    if path is None:
        return None
    if path.is_relative_to(DATA_DIR):
        return f"/data/qr/{path.name}"
    return f"/data/qr/{path.name}"


def _pick_flight(origin: str, dest: str, start_date: str | None) -> dict | None:
    data = _load_json("zalopay_flight_est_price.json")
    estimates = data.get("estimates") or []
    matches = [
        e
        for e in estimates
        if e.get("departure_airport") == origin and e.get("arrival_airport") == dest
    ]
    matches = _filter_by_week(matches, iso_week_label(start_date))
    if not matches:
        return None
    economy = [
        e
        for e in matches
        if "economy" in (e.get("fare_class") or "").lower()
    ]
    pool = economy or matches
    pool.sort(key=lambda e: _safe_price(e.get("est_total_price_vnd")))
    best = pool[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('airline_name', 'Bay nội địa')} · {best.get('fare_class', 'Economy')}",
        type_label="Máy bay",
        price_min=_safe_price(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_safe_price(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/khứ hồi",
        note=f"{origin} → {dest} · dữ liệu Zalopay",
        is_zalopay=True,
    )


def _pick_train(origin: str, dest: str, start_date: str | None = None) -> dict | None:
    data = _load_json("zalopay_train_est_price.json")
    estimates = data.get("estimates") or []
    matches = [
        e
        for e in estimates
        if e.get("from_code") == origin and e.get("to_code") == dest
    ]
    matches = _filter_by_week(matches, iso_week_label(start_date))
    if not matches:
        return None
    matches.sort(key=lambda e: _safe_price(e.get("est_total_price_vnd")))
    best = matches[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('train_name', 'Tàu')} · {best.get('seat_type_label', 'Ghế ngồi')}",
        type_label="Tàu hỏa",
        price_min=_safe_price(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_safe_price(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/người",
        note=f"{best.get('from_name', origin)} → {best.get('to_name', dest)}",
        is_zalopay=True,
    )


def _pick_bus(origin: str, dest: str, start_date: str | None = None) -> dict | None:
    data = _load_json("zalopay_bus_est_price.json")
    estimates = data.get("estimates") or []
    matches = [
        e
        for e in estimates
        if e.get("from_code") == origin and e.get("to_code") == dest
    ]
    matches = _filter_by_week(matches, iso_week_label(start_date))
    if not matches:
        return None
    matches.sort(key=lambda e: _safe_price(e.get("est_total_price_vnd")))
    best = matches[0]
    return _option(
        provider="Zalopay",
        name=f"{best.get('operator_name', 'Xe khách')} · {best.get('seat_type', 'Ghế')}",
        type_label="Xe khách",
        price_min=_safe_price(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_safe_price(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/người",
        note=f"{best.get('from_name', origin)} → {best.get('to_name', dest)}",
        is_zalopay=True,
    )


def _pick_hotel(dest: str, start_date: str | None) -> dict | None:
    data = _load_json("zalopay_hotel_est_price.json")
    estimates = data.get("estimates") or []
    matches = [e for e in estimates if e.get("hotel_city_code") == dest]
    matches = _filter_by_week(matches, iso_week_label(start_date))
    if not matches:
        return None
    by_hotel: dict[str, dict] = {}
    for row in matches:
        hid = row.get("hotel_id") or row.get("hotel_name")
        if hid not in by_hotel or _safe_price(row.get("est_total_price_vnd")) < _safe_price(
            by_hotel[hid].get("est_total_price_vnd")
        ):
            by_hotel[hid] = row
    best = min(by_hotel.values(), key=lambda e: _safe_price(e.get("est_total_price_vnd")))
    return _option(
        provider="Zalopay",
        name=f"{best.get('hotel_name', 'Khách sạn')} · {best.get('room_type', 'Standard')}",
        type_label="Lưu trú",
        price_min=_safe_price(best.get("min_total_price_vnd") or best.get("est_total_price_vnd")),
        price_max=_safe_price(best.get("max_total_price_vnd") or best.get("est_total_price_vnd")),
        unit="/đêm",
        note=best.get("breakfast_option") or best.get("hotel_city") or dest,
        is_zalopay=True,
    )


def _route_band(origin: str, dest: str) -> dict | None:
    data = _load_json("vn_flight_estimates.json")
    routes = data.get("routes") or {}
    return routes.get(f"{origin}-{dest}")


def _brand_mid(category: str, brand: dict, band: dict | None, origin: str, dest: str) -> int:
    provider = brand["provider"]
    if category == "flight" and band:
        fn = FLIGHT_BRAND_MID.get(provider, lambda b: b["mid"])
        return _round_hundreds(fn(band))
    if category == "train":
        trains = (_load_json("vn_flight_estimates.json").get("train_estimates") or {})
        tb = trains.get(f"{origin}-{dest}") or {}
        base = _round_hundreds(tb.get("mid") or tb.get("low") or 700_000)
        offset = TRAIN_BRAND_OFFSET.get(provider, 0)
        return _round_hundreds(base + offset)
    if category == "bus":
        return BUS_BRAND_MID.get(provider, 420_000)
    if category == "hotel":
        return HOTEL_BRAND_MID.get(provider, 800_000)
    preset_min = brand.get("priceMin")
    preset_max = brand.get("priceMax")
    if preset_min is not None and preset_max is not None:
        return _round_hundreds((int(preset_min) + int(preset_max)) // 2)
    return 500_000


def _brand_options(category: str, origin: str, dest: str, limit: int = 3) -> list[dict]:
    band = _route_band(origin, dest) if category == "flight" else None
    options = []
    for brand in BRAND_FALLBACKS.get(category, [])[:limit]:
        mid = _brand_mid(category, brand, band, origin, dest)
        price_min, price_max = _mid_range(mid)
        options.append(
            _option(
                provider=brand["provider"],
                name=brand["provider"],
                type_label=brand["type"],
                price_min=price_min,
                price_max=price_max,
                unit=brand.get("unit", "/người"),
                note=brand.get("note", ""),
                url=brand.get("url"),
            )
        )
    return options


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


def _category(
    category_id: str,
    title: str,
    type_label: str,
    zalopay_option: dict | None,
    brand_category: str,
    origin: str,
    dest: str,
) -> dict:
    if zalopay_option:
        options = [zalopay_option] + _brand_options(brand_category, origin, dest, limit=3)
    else:
        options = _brand_options(brand_category, origin, dest, limit=3)
        qr_option = _zalopay_qr_option(category_id, type_label)
        if qr_option:
            options.append(qr_option)
    return {
        "id": category_id,
        "title": title,
        "options": options[:4],
    }


def build_estimates(payload: dict) -> dict:
    brief = payload.get("trip_brief") or {}
    origin_name = brief.get("origin_city") or ""
    dest_name = brief.get("destination_city") or ""
    origin = city_to_code(origin_name)
    dest = city_to_code(dest_name)
    start_date = brief.get("start_date")

    categories = []
    if origin and dest:
        categories.extend(
            [
                _category(
                    "flight",
                    "✈️ Máy bay",
                    "Máy bay",
                    _pick_flight(origin, dest, start_date),
                    "flight",
                    origin,
                    dest,
                ),
                _category(
                    "train",
                    "🚆 Tàu hỏa",
                    "Tàu hỏa",
                    _pick_train(origin, dest, start_date),
                    "train",
                    origin,
                    dest,
                ),
                _category(
                    "bus",
                    "🚌 Xe khách",
                    "Xe khách",
                    _pick_bus(origin, dest, start_date),
                    "bus",
                    origin,
                    dest,
                ),
            ]
        )
    if dest:
        categories.append(
            _category(
                "hotel",
                "🏨 Lưu trú",
                "Lưu trú",
                _pick_hotel(dest, start_date),
                "hotel",
                origin or "SGN",
                dest,
            )
        )

    categories.append(
        {
            "id": "local",
            "title": "🛵 Tại điểm đến",
            "options": _brand_options("local", origin or "SGN", dest or "DAD", limit=4)[:4],
        }
    )
    categories.append(
        {
            "id": "activity",
            "title": "🎯 Thư giãn & vui chơi",
            "options": _brand_options("activity", origin or "SGN", dest or "DAD", limit=4)[:4],
        }
    )

    budget = payload.get("budget_ledger") or {}
    return {
        "originCode": origin,
        "destCode": dest,
        "categories": categories,
        "budget": budget,
    }
