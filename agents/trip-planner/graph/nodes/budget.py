from __future__ import annotations

import math

from models.budget import BudgetLedger, CategoryBudget
from models.trip_brief import TripBrief
from tools.geo import _load_json


def _pick_stay_tier(stays: list[dict]) -> str:
    if not stays:
        return "default"
    types = [s.get("type", "default") for s in stays]
    if any("hostel" in t for t in types):
        return "hostel"
    if any("5star" in t for t in types):
        return "hotel_5star"
    if any("4star" in t for t in types):
        return "hotel_4star"
    if any("3star" in t for t in types):
        return "hotel_3star"
    if any("guest_house" in t for t in types):
        return "guest_house"
    return "default"


def build_budget_ledger(
    brief: TripBrief,
    stay_results: dict,
    transport_results: dict,
    activity_results: dict,
) -> BudgetLedger:
    bands = _load_json("vn_price_bands.json")
    headcount = brief.headcount
    nights = brief.nights or brief.compute_nights() or 1
    rooms = math.ceil(headcount / 2)

    stay_tier = _pick_stay_tier(stay_results.get("stays", []))
    nightly = bands["stay_nightly_per_room"].get(
        stay_tier, bands["stay_nightly_per_room"]["default"]
    )
    stay_cost = {
        tier: nightly[tier] * rooms * nights for tier in ("low", "mid", "high")
    }
    stay_per_person = {tier: stay_cost[tier] // headcount for tier in stay_cost}

    transport_options = transport_results.get("options", [])
    transport_mid = 0
    transport_notes = "No transport options"
    transport_source = "estimate"
    if transport_options:
        recommended_mode = transport_results.get("recommended_mode")
        rec = next(
            (o for o in transport_options if o.get("mode") == recommended_mode),
            transport_options[0],
        )
        if "cost_vnd_total" in rec:
            transport_cost = rec["cost_vnd_total"]
        else:
            transport_cost = rec.get("cost_vnd", {"low": 0, "mid": 0, "high": 0})
        transport_per_person = {
            tier: transport_cost[tier] // headcount for tier in ("low", "mid", "high")
        }
        transport_mid = transport_per_person["mid"]
        transport_notes = f"Recommended: {rec.get('mode', 'unknown')} — {rec.get('notes', rec.get('route', ''))}"
        transport_source = rec.get("source", "estimate")
    else:
        transport_per_person = {"low": 0, "mid": 0, "high": 0}

    food_bands = bands["food_per_person_per_day"]
    food_per_person = {
        tier: food_bands[tier] * nights for tier in ("low", "mid", "high")
    }

    act_bands = bands["activities_per_person_per_day"]
    free_count = sum(
        1 for a in activity_results.get("activities", []) if a.get("fee") == "no"
    )
    activity_per_person = {
        tier: act_bands[tier] * nights for tier in ("low", "mid", "high")
    }
    if free_count >= nights:
        activity_per_person = {tier: max(v // 2, 0) for tier, v in activity_per_person.items()}

    categories = {
        "transport": CategoryBudget(
            low=transport_per_person["low"],
            mid=transport_per_person["mid"],
            high=transport_per_person["high"],
            notes=transport_notes,
            source=transport_source,
        ),
        "stay": CategoryBudget(
            low=stay_per_person["low"],
            mid=stay_per_person["mid"],
            high=stay_per_person["high"],
            notes=f"{rooms} rooms × {nights} nights ({stay_tier})",
            source=stay_results.get("source", "osm"),
            room_count=rooms,
        ),
        "activities": CategoryBudget(
            low=activity_per_person["low"],
            mid=activity_per_person["mid"],
            high=activity_per_person["high"],
            notes=f"{activity_results.get('count', 0)} POIs found; {free_count} likely free",
            source=activity_results.get("source", "osm"),
        ),
        "food": CategoryBudget(
            low=food_per_person["low"],
            mid=food_per_person["mid"],
            high=food_per_person["high"],
            notes=f"{nights} days × per-person food bands",
            source="estimate",
        ),
    }

    subtotal = {
        tier: sum(categories[c].model_dump()[tier] for c in categories)
        for tier in ("low", "mid", "high")
    }
    contingency_pct = 10
    total_per_person = {
        tier: int(subtotal[tier] * (1 + contingency_pct / 100)) for tier in subtotal
    }
    total_group = {tier: total_per_person[tier] * headcount for tier in total_per_person}

    warnings: list[str] = []
    tradeoffs: list[str] = []
    budget_cap = brief.budget_vnd

    if budget_cap:
        if categories["stay"].mid > budget_cap * 0.45:
            warnings.append("Stay (mid) exceeds 45% of per-person budget — consider hostels or fewer nights")
        if categories["transport"].mid > budget_cap * 0.35:
            warnings.append("Transport (mid) exceeds 35% of budget — consider train or shared car")
        if total_per_person["mid"] > budget_cap:
            warnings.append(
                f"Estimated mid total {total_per_person['mid']:,} VND exceeds budget {budget_cap:,} VND/person"
            )
            tradeoffs = [
                "Shorten the trip by 1 night",
                "Choose a closer destination or train instead of flying",
                "Pick budget stays (hostel/guest house)",
                "Focus on free outdoor activities",
            ]

    return BudgetLedger(
        headcount=headcount,
        categories={k: v for k, v in categories.items()},
        contingency_pct=contingency_pct,
        total_per_person=total_per_person,
        total_group=total_group,
        warnings=warnings,
        over_budget=bool(budget_cap and total_per_person["mid"] > budget_cap),
        tradeoff_options=tradeoffs,
    )
