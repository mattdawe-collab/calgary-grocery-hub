"""
Send a Calgary Grocery Hub deal digest to Telegram.

Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env unless --dry-run or
--get-updates is used. The script is intentionally independent from the scraper
so it can be run manually, scheduled after weekly refreshes, or tested safely.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv
from data_quality import add_quality_metadata, filter_grocery_relevant, repair_category, sanitize_unit_prices
from deal_guidance import (
    ACTION_BUY,
    ACTION_COMPARE,
    ACTION_STOCK_UP,
    add_deal_guidance,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT = Path(__file__).resolve().parent
CURRENT_FLYERS = ROOT / "current_flyers.csv"
TELEGRAM_LIMIT = 4096
SAFE_CHUNK_SIZE = 3600

CATEGORY_GROUPS = {
    "proteins": {
        "title": "Calgary Protein Deals",
        "label": "protein items",
        "categories": ["Beef", "Pork", "Poultry", "Lamb", "Seafood"],
    },
}


def _load_env() -> None:
    load_dotenv(ROOT / ".env", override=True)


def _public_dashboard_url() -> str:
    explicit = os.getenv("PUBLIC_DASHBOARD_URL") or os.getenv("DASHBOARD_PUBLIC_URL")
    if explicit:
        return explicit.rstrip("/")
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        return f"https://{railway_domain.strip('/')}"
    return ""


def _deal_snapshot_url(deal_id) -> str:
    base_url = _public_dashboard_url()
    if not base_url or deal_id is None:
        return ""
    return f"{base_url}/share/deals/{quote(str(deal_id))}"


def _money(value) -> str:
    try:
        if pd.isna(value):
            return "n/a"
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _calendar_date(value, include_year: bool = False) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value)
    try:
        dt = pd.to_datetime(text, errors="raise")
        fmt = "%b %-d, %Y" if include_year else "%b %-d"
        if os.name == "nt":
            fmt = "%b %#d, %Y" if include_year else "%b %#d"
        return dt.strftime(fmt)
    except Exception:
        return text[:10]


def _modal_date_text(values: pd.Series) -> str:
    dates = values.dropna().astype(str).str.slice(0, 10)
    if dates.empty:
        return ""
    mode = dates.mode()
    return str(mode.iloc[0] if not mode.empty else dates.max())


def _flyer_window(df: pd.DataFrame) -> tuple[str, str, str | None]:
    valid_from = _modal_date_text(df.get("Valid_From", pd.Series(dtype=str)))
    valid_until = _modal_date_text(df.get("Valid_Until", pd.Series(dtype=str)))

    all_until = df.get("Valid_Until", pd.Series(dtype=str)).dropna().astype(str).str.slice(0, 10)
    long_until = None
    if not all_until.empty:
        max_until = str(all_until.max())
        if valid_until and max_until != valid_until:
            long_until = max_until

    return (
        _calendar_date(valid_from),
        _calendar_date(valid_until, include_year=True),
        _calendar_date(long_until, include_year=True) if long_until else None,
    )


def _shorten(value, limit: int = 64) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _why_list(row: pd.Series, limit: int = 2) -> list[str]:
    value = row.get("why_bullets", "")
    if isinstance(value, list):
        bullets = [str(v).strip() for v in value if str(v).strip()]
    else:
        bullets = [part.strip() for part in str(value or "").split(";") if part.strip()]
    return bullets[:limit]


def _deal_label(row: pd.Series, rank: int | None = None, deal_id=None) -> str:
    score = row.get("deal_score", row.get("ai_deal_score", 0))
    try:
        score_text = f"{float(score):.0f}"
    except (TypeError, ValueError):
        score_text = "?"

    confidence = row.get("confidence_score", 0)
    try:
        confidence_text = f"{float(confidence):.0f}"
    except (TypeError, ValueError):
        confidence_text = "?"

    item_text = html.escape(_shorten(row.get("Item", ""), 64))
    item_url = _deal_snapshot_url(deal_id)
    item = f'<a href="{html.escape(item_url, quote=True)}">{item_text}</a>' if item_url else f"<b>{item_text}</b>"
    store = html.escape(str(row.get("Store", "")).strip())
    price = html.escape(_money(row.get("Price_Value")))

    unit = ""
    unit_price = row.get("unit_price")
    unit_type = row.get("unit_type")
    try:
        if pd.notna(unit_price) and unit_type:
            unit_name = str(unit_type).replace("$/", "/")
            unit = html.escape(f" ({_money(unit_price)}{unit_name})")
    except (TypeError, ValueError):
        pass

    prefix = f"{rank}. " if rank else "* "
    lines = [
        f"{prefix}{item}",
        f"   {price}{unit} at {store} | score {score_text}, confidence {confidence_text}",
    ]

    why = [html.escape(part) for part in _why_list(row)]
    if why:
        lines.append(f"   {' | '.join(why)}")
    return "\n".join(lines)


def _prepare_current_deals() -> pd.DataFrame:
    if not CURRENT_FLYERS.exists():
        raise FileNotFoundError(f"{CURRENT_FLYERS} not found")

    df = pd.read_csv(CURRENT_FLYERS, low_memory=False)
    if df.empty:
        return df

    df, _ = filter_grocery_relevant(df)
    df, _ = sanitize_unit_prices(df)
    categories = df.apply(
        lambda row: repair_category(row.get("Item", ""), row.get("ai_category", "Other")),
        axis=1,
        result_type="expand",
    )
    df["display_category"] = categories[0]
    df["category_source"] = categories[1]
    return add_deal_guidance(add_quality_metadata(df))


def _filter_deals(
    df: pd.DataFrame,
    min_score: float,
    store: str | None,
    category: str | None,
    category_group: str | None = None,
) -> pd.DataFrame:
    score_col = "deal_score" if "deal_score" in df.columns else "ai_deal_score"
    df = df.copy()
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)

    if store:
        df = df[df["Store"].astype(str).str.casefold() == store.casefold()]
    category_col = "display_category" if "display_category" in df.columns else "ai_category"
    if category_group:
        group = CATEGORY_GROUPS.get(category_group)
        if group and category_col in df.columns:
            df = df[df[category_col].isin(group["categories"])]
    if category and category_col in df.columns:
        df = df[df[category_col].astype(str).str.casefold() == category.casefold()]
    df = df[df[score_col] >= min_score]

    sort_cols = [score_col]
    ascending = [False]
    if "pct_below_avg" in df.columns:
        df["pct_below_avg"] = pd.to_numeric(df["pct_below_avg"], errors="coerce").fillna(0)
        sort_cols.append("pct_below_avg")
        ascending.append(False)
    if "Price_Value" in df.columns:
        df["Price_Value"] = pd.to_numeric(df["Price_Value"], errors="coerce")
        sort_cols.append("Price_Value")
        ascending.append(True)

    return df.sort_values(sort_cols, ascending=ascending, na_position="last")


def _action_summary(df: pd.DataFrame) -> str:
    if df.empty or "action_label" not in df.columns:
        return "No matching deals."
    counts = df["action_label"].value_counts()
    stock_up = int(counts.get(ACTION_STOCK_UP, 0))
    buy = int(counts.get(ACTION_BUY, 0))
    compare = int(counts.get(ACTION_COMPARE, 0))
    if not any([stock_up, buy, compare]):
        return "Plan: no high-priority actions."
    return f"Plan: {stock_up} stock-up | {buy} buy | {compare} compare"


def _top_store_summary(df: pd.DataFrame) -> str:
    if df.empty or "Store" not in df.columns:
        return ""
    action_df = df[df.get("action_label", pd.Series(dtype=str)).isin([ACTION_STOCK_UP, ACTION_BUY])]
    if action_df.empty:
        action_df = df
    grouped = (
        action_df.groupby("Store")
        .agg(count=("Item", "count"), avg_score=("deal_score", "mean"))
        .sort_values(["count", "avg_score"], ascending=[False, False])
        .head(2)
    )
    if grouped.empty:
        return ""
    return "Best stops: " + " | ".join(
        f"{store}: {int(row['count'])} picks, avg {row['avg_score']:.0f}"
        for store, row in grouped.iterrows()
    )


def _category_mix_summary(df: pd.DataFrame) -> str:
    if df.empty or "display_category" not in df.columns:
        return ""
    counts = df["display_category"].value_counts().head(5)
    return "Mix: " + " | ".join(f"{cat}: {int(count)}" for cat, count in counts.items())


def _append_section(lines: list[str], title: str, df: pd.DataFrame, limit: int) -> int:
    if limit <= 0 or df.empty:
        return 0
    lines.append("")
    lines.append(f"<b>{html.escape(title)}</b>")
    used = 0
    for _, row in df.head(limit).iterrows():
        used += 1
        lines.append(_deal_label(row, used, row.name))
    return used


def build_digest(
    limit: int,
    min_score: float,
    store: str | None = None,
    category: str | None = None,
    category_group: str | None = None,
) -> str:
    df = _prepare_current_deals()
    if df.empty:
        return "Calgary Grocery Hub\n\nNo current flyer deals found."

    group = CATEGORY_GROUPS.get(category_group or "")
    context_df = df
    context_label = "grocery items"
    if group:
        context_df = df[df["display_category"].isin(group["categories"])]
        context_label = group["label"]

    filtered = _filter_deals(
        df,
        min_score=min_score,
        store=store,
        category=category,
        category_group=category_group,
    )
    valid_from, valid_until, long_until = _flyer_window(df)

    title_bits = [group["title"] if group else "Calgary grocery deals"]
    if store:
        title_bits.append(store)
    if category:
        title_bits.append(category)

    lines = [
        f"<b>{html.escape(' - '.join(title_bits)).title()}</b>",
        f"{html.escape(valid_from)} - {html.escape(valid_until)}",
        "",
        f"{len(filtered):,} strong picks from {len(context_df):,} {context_label}",
        html.escape(_action_summary(filtered)),
    ]
    if long_until:
        lines.append(f"Long-running flyer to {html.escape(long_until)}.")

    store_summary = _top_store_summary(filtered)
    if store_summary:
        lines.append(html.escape(store_summary))
    if group:
        mix_summary = _category_mix_summary(filtered)
        if mix_summary:
            lines.append(html.escape(mix_summary))

    if "ai_confidence" in df.columns:
        fallback = int((df["ai_confidence"].astype(str) == "statistical").sum())
        if 0 < fallback < len(df):
            lines.append(f"AI note: {fallback:,}/{len(df):,} items used statistical fallback scoring.")

    if filtered.empty:
        lines.append("")
        lines.append("No deals matched this filter.")
    else:
        stock_up = filtered[filtered["action_label"] == ACTION_STOCK_UP]
        buy = filtered[filtered["action_label"] == ACTION_BUY]
        compare = filtered[filtered["action_label"] == ACTION_COMPARE]

        remaining = max(1, limit)
        stock_limit = min(5, len(stock_up), remaining)
        remaining -= stock_limit
        buy_limit = min(4, len(buy), remaining)
        remaining -= buy_limit
        compare_limit = min(3, len(compare), remaining)
        remaining -= compare_limit

        if remaining > 0 and buy_limit < len(buy):
            extra = min(remaining, len(buy) - buy_limit)
            buy_limit += extra
            remaining -= extra
        if remaining > 0 and stock_limit < len(stock_up):
            extra = min(remaining, len(stock_up) - stock_limit)
            stock_limit += extra
            remaining -= extra
        if remaining > 0 and compare_limit < len(compare):
            compare_limit += min(remaining, len(compare) - compare_limit)

        shown = 0
        shown += _append_section(lines, "Stock up now", stock_up, stock_limit)
        shown += _append_section(lines, ACTION_BUY, buy, buy_limit)
        shown += _append_section(lines, ACTION_COMPARE, compare, compare_limit)

        if shown == 0:
            _append_section(lines, "Top deals", filtered, min(limit, len(filtered)))

    lines.append("")
    lines.append(f"Generated {html.escape(datetime.now().strftime('%Y-%m-%d %H:%M'))}")
    return "\n".join(lines)


def chunk_message(message: str) -> Iterable[str]:
    if len(message) <= TELEGRAM_LIMIT:
        yield message
        return

    current: list[str] = []
    current_len = 0
    for line in message.splitlines():
        add_len = len(line) + 1
        if current and current_len + add_len > SAFE_CHUNK_SIZE:
            yield "\n".join(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += add_len
    if current:
        yield "\n".join(current)


def telegram_request(method: str, token: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if method == "getUpdates":
        response = requests.get(url, timeout=30)
    else:
        response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API returned ok=false: {data}")
    return data


def send_digest(message: str, token: str, chat_id: str, disable_notification: bool = False) -> int:
    sent = 0
    for chunk in chunk_message(message):
        telegram_request(
            "sendMessage",
            token,
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": disable_notification,
            },
        )
        sent += 1
    return sent


def print_updates(token: str) -> None:
    data = telegram_request("getUpdates", token)
    updates = data.get("result", [])
    if not updates:
        print("No updates found. Send a message to your bot in Telegram, then run this again.")
        return
    for update in updates[-10:]:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat", {})
        print(f"chat_id={chat.get('id')} type={chat.get('type')} title={chat.get('title') or chat.get('username') or chat.get('first_name')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Calgary Grocery Hub deals to Telegram.")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest instead of sending it.")
    parser.add_argument("--optional", action="store_true", help="Skip without failing when Telegram env vars are missing.")
    parser.add_argument("--get-updates", action="store_true", help="Print recent Telegram chat IDs for this bot token.")
    parser.add_argument("--limit", type=int, default=int(os.getenv("TELEGRAM_DIGEST_LIMIT", "12")))
    parser.add_argument("--min-score", type=float, default=float(os.getenv("TELEGRAM_MIN_SCORE", "80")))
    parser.add_argument("--store", default=os.getenv("TELEGRAM_STORE_FILTER") or None)
    parser.add_argument("--category", default=os.getenv("TELEGRAM_CATEGORY_FILTER") or None)
    parser.add_argument("--group", choices=sorted(CATEGORY_GROUPS), help="Send a focused category-group digest.")
    parser.add_argument("--silent", action="store_true", help="Send without a Telegram notification sound.")
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if args.get_updates:
        if not token:
            print("TELEGRAM_BOT_TOKEN is required for --get-updates")
            return 2
        print_updates(token)
        return 0

    message = build_digest(
        limit=max(1, args.limit),
        min_score=args.min_score,
        store=args.store,
        category=args.category,
        category_group=args.group,
    )

    if args.dry_run:
        print(message)
        return 0

    if not token or not chat_id:
        msg = "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required to send Telegram messages."
        if args.optional:
            print(f"[telegram skipped] {msg}")
            return 0
        print(msg)
        return 2

    sent = send_digest(message, token=token, chat_id=chat_id, disable_notification=args.silent)
    print(f"Sent {sent} Telegram message(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
