"""
Shopper-facing deal guidance for Calgary Grocery Hub.

`deal_score` answers whether the price is attractive. This module adds the
separate question shoppers actually need: how confidently should I act on it?
"""

from __future__ import annotations

from typing import Any

import pandas as pd


ACTION_STOCK_UP = "Stock up"
ACTION_BUY = "Buy this week"
ACTION_COMPARE = "Compare first"
ACTION_ONLY_IF_NEEDED = "Only if needed"
ACTION_SKIP = "Skip"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "y"}
    return bool(value)


def _has_value(value: Any) -> bool:
    try:
        return not pd.isna(value)
    except (TypeError, ValueError):
        return value is not None


def _quality_flag_set(flags: Any) -> set[str]:
    return {
        part.strip()
        for part in str(flags or "").split(";")
        if part and part.strip() and part.strip().casefold() != "nan"
    }


def confidence_score(row: Any) -> int:
    """Score the evidence behind a recommendation from 0 to 100."""
    score = 35

    hist_count = int(_num(row.get("historical_count"), 0))
    if hist_count >= 20:
        score += 25
    elif hist_count >= 10:
        score += 22
    elif hist_count >= 5:
        score += 18
    elif hist_count >= 3:
        score += 14
    elif hist_count >= 1:
        score += 8

    if _has_value(row.get("pct_below_avg")):
        score += 8
    if _has_value(row.get("price_percentile")):
        score += 5

    cross_count = int(_num(row.get("cross_store_count"), 0))
    cross_rank = _num(row.get("cross_store_rank"), 0)
    if cross_count >= 3:
        score += 12
    elif cross_count == 2:
        score += 8
    if cross_count > 1 and 1 <= cross_rank <= cross_count:
        score += 3

    if _has_value(row.get("unit_price")):
        score += 8

    category_source = str(row.get("category_source", "") or "").casefold()
    if category_source == "ai":
        score += 4
    elif category_source == "fallback":
        score -= 8

    data_quality = _num(row.get("data_quality_score"), 100)
    if data_quality < 80:
        score -= min(20, int((80 - data_quality) / 2))

    flags = _quality_flag_set(row.get("quality_flags"))
    if "unit_price_outlier" in flags or "unit_price_invalid" in flags:
        score -= 12
    if "no_history" in flags:
        score -= 10

    return max(0, min(100, int(round(score))))


def action_label(row: Any) -> str:
    """Convert value score plus confidence into a shopper action."""
    score = _num(row.get("deal_score", row.get("ai_deal_score")), 0)
    confidence = _num(row.get("confidence_score"), confidence_score(row))
    hist_count = _num(row.get("historical_count"), 0)

    if score >= 88 and confidence >= 72 and hist_count >= 3:
        return ACTION_STOCK_UP
    if score >= 76 and confidence >= 58:
        return ACTION_BUY
    if score >= 70:
        return ACTION_COMPARE
    if score >= 50:
        return ACTION_ONLY_IF_NEEDED
    return ACTION_SKIP


def why_bullets(row: Any, limit: int = 3) -> list[str]:
    """Return compact evidence bullets for cards, reports, and Telegram."""
    bullets: list[str] = []

    pct_below = row.get("pct_below_avg")
    if _has_value(pct_below):
        pct = _num(pct_below)
        hist_avg = row.get("historical_avg")
        if pct >= 5:
            if _has_value(hist_avg):
                bullets.append(f"{pct:.0f}% below avg ${_num(hist_avg):.2f}")
            else:
                bullets.append(f"{pct:.0f}% below average")
        elif pct <= -5:
            bullets.append(f"{abs(pct):.0f}% above average")

    if _bool(row.get("is_lowest_historical")):
        bullets.append("Lowest seen")

    cross_rank = row.get("cross_store_rank")
    cross_count = int(_num(row.get("cross_store_count"), 0))
    if _has_value(cross_rank) and cross_count > 1:
        rank = int(_num(cross_rank))
        if rank == 1:
            bullets.append(f"Cheapest of {cross_count} stores")
        elif rank <= 3:
            bullets.append(f"#{rank} of {cross_count} stores")

    hist_count = int(_num(row.get("historical_count"), 0))
    if hist_count >= 3:
        bullets.append(f"{hist_count} prior prices")
    elif hist_count > 0:
        bullets.append(f"Only {hist_count} prior price{'s' if hist_count != 1 else ''}")
    else:
        bullets.append("No price history")

    if _has_value(row.get("unit_price")):
        unit_type = row.get("unit_type") or ""
        bullets.append(f"Unit price checked {unit_type}".strip())

    if str(row.get("category_source", "") or "").casefold() in {"inferred", "corrected", "fallback"}:
        bullets.append("Category reviewed")

    seen: set[str] = set()
    unique = []
    for bullet in bullets:
        if bullet not in seen:
            seen.add(bullet)
            unique.append(bullet)
        if len(unique) >= limit:
            break
    return unique


def add_deal_guidance(df: pd.DataFrame) -> pd.DataFrame:
    """Add confidence, action, and why columns to a deal dataframe."""
    if df.empty:
        return df

    df = df.copy()
    df["confidence_score"] = df.apply(confidence_score, axis=1)
    df["action_label"] = df.apply(action_label, axis=1)
    df["why_bullets"] = df.apply(lambda row: "; ".join(why_bullets(row)), axis=1)
    return df
