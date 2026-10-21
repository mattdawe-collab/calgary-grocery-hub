"""
Build the public "This Week's Deals" page for GitHub Pages.

Design brief (from the owner): comprehensive for details, accessible at a
glance. So the page has two layers:

  * At a glance: the week's verdict, a ranked "top of the board", and one
    card per store with its strongest deals.
  * Comprehensive: every single flyer deal is on the page. Search, store /
    category / score filters, "show all" per store, and every row expands to
    its evidence (history, cross-store rank, why bullets) plus a link to its
    price-history card.

Everything is rendered server-side (works without JavaScript); the JS only
filters what is already in the DOM.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from html import escape

import pandas as pd

from data_quality import PARENT_COMPANY, infer_price_basis, parse_dates

STORE_SHORT = {
    "Real Canadian Superstore": "Superstore",
    "No Frills": "No Frills",
    "Save-On-Foods": "Save-On",
    "Calgary Co-op": "Co-op",
    "Sobeys": "Sobeys",
    "Safeway": "Safeway",
    "Walmart": "Walmart",
}

PROTEINS = ["Pork", "Poultry", "Beef", "Seafood", "Lamb"]
FOOD_CATEGORIES = PROTEINS + ["Produce", "Dairy & Eggs", "Bakery", "Pantry", "Frozen", "Snacks", "Beverages"]
CATEGORY_ORDER = FOOD_CATEGORIES + ["Household & Personal", "Pet", "Prepared Foods", "Other"]
STRONG_SCORE = 80


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
def _num(value, default=None):
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _modal_day(series: pd.Series) -> str | None:
    """Most common calendar day as written (never converted through UTC)."""
    days = parse_dates(series).dropna()
    if days.empty:
        return None
    return days.dt.strftime("%Y-%m-%d").mode().iloc[0]


def _pretty_date(value: str | None, with_year: bool = False) -> str:
    if not value:
        return ""
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return value
    return ts.strftime("%b %-d, %Y" if with_year else "%b %-d") if os.name != "nt" else ts.strftime("%b %d, %Y" if with_year else "%b %d").replace(" 0", " ")


def _verdict(avg_score: float, strong: int) -> str:
    if avg_score >= 65 or strong >= 25:
        return "Hot"
    if avg_score >= 55 or strong >= 12:
        return "Solid"
    if avg_score >= 45 or strong >= 4:
        return "Average"
    return "Weak"


def _cross_store_text(rank, count) -> str:
    rank, count = _num(rank), _num(count)
    if not rank or not count or count <= 1:
        return ""
    rank, count = int(rank), int(count)
    if rank == 1:
        return f"cheapest of {count} stores"
    return f"#{rank} of {count} stores"


def _deal_record(deal_id, row: pd.Series, modal_until: str | None, base_url: str) -> dict:
    price = _num(row.get("Price_Value"), 0.0)
    score = _num(row.get("deal_score"), 0.0)
    avg = _num(row.get("historical_avg"))
    pct = _num(row.get("pct_below_avg"))
    hist_n = int(_num(row.get("historical_count"), 0) or 0)
    why_raw = row.get("why_bullets")
    why = [w.strip() for w in str(why_raw).split(";") if w and w.strip()] if isinstance(why_raw, str) and why_raw else []
    unit = ""
    if _num(row.get("unit_price")) and isinstance(row.get("unit_type"), str) and row.get("unit_type"):
        unit = f"${_num(row.get('unit_price')):.2f}{row.get('unit_type')}"
    until = None
    if isinstance(row.get("Valid_Until"), str) or pd.notna(row.get("Valid_Until")):
        ts = parse_dates(pd.Series([row.get("Valid_Until")])).iloc[0]
        until = ts.strftime("%Y-%m-%d") if pd.notna(ts) else None
    store = str(row.get("Store") or "")
    category = str(row.get("display_category") or row.get("ai_category") or "Other")
    # Flipp sends no unit, so a meat price may be per pound. Say so on the row
    # rather than printing a bare number a shopper cannot compare.
    basis = infer_price_basis(
        row.get("Item"), category, price, row.get("price_basis"), row.get("unit_price")
    )
    price_label = f"{_money(price)}/lb" if basis == "per_lb" else _money(price)
    history_unit = str(row.get("history_unit") or "").replace("$/", "/")
    avg_label = f"{_money(avg)}{history_unit}" if avg is not None else ""
    return {
        "basis": basis,
        "price_label": price_label,
        "avg_label": avg_label,
        "id": int(deal_id),
        "item": str(row.get("Item") or "").strip(),
        "store": store,
        "store_short": STORE_SHORT.get(store, store),
        "category": category,
        "price": round(price, 2),
        "unit": unit,
        "score": round(score),
        "action": str(row.get("action_label") or ""),
        "pct_below_avg": round(pct) if pct is not None else None,
        "avg": round(avg, 2) if avg is not None else None,
        "hist_count": hist_n,
        "lowest": bool(row.get("is_lowest_historical", False)),
        "cross_store": _cross_store_text(row.get("cross_store_rank"), row.get("cross_store_count")),
        "why": why,
        "confidence": round(_num(row.get("confidence_score"), 0) or 0),
        "valid_until": until,
        "long_flyer": bool(until and modal_until and until != modal_until),
        "also_at": "",
        "url": f"{base_url}share/deals/{int(deal_id)}/",
    }


def build_page_model(df: pd.DataFrame, latest: dict | None, base_url: str) -> dict:
    base_url = base_url.rstrip("/") + "/"
    df = df.copy()
    if "display_category" not in df.columns:
        df["display_category"] = df.get("ai_category", "Other")
    df["deal_score"] = pd.to_numeric(df.get("deal_score"), errors="coerce").fillna(0)

    modal_until = _modal_day(df["Valid_Until"]) if "Valid_Until" in df.columns else None
    modal_from = _modal_day(df["Valid_From"]) if "Valid_From" in df.columns else None

    deals = [_deal_record(idx, row, modal_until, base_url) for idx, row in df.iterrows()]
    deals.sort(key=lambda d: (-d["score"], -(d["pct_below_avg"] or 0), d["item"]))

    # Store summaries, strongest first.
    stores = []
    for store, group in df.groupby("Store"):
        food = group[group["display_category"].isin(FOOD_CATEGORIES)]
        scored = food if len(food) else group
        strong = int((scored["deal_score"] >= STRONG_SCORE).sum())
        avg_score = float(scored["deal_score"].mean()) if len(scored) else 0.0
        cats = (
            scored[scored["deal_score"] >= STRONG_SCORE]["display_category"].value_counts().head(3).index.tolist()
        )
        stores.append({
            "name": store,
            "short": STORE_SHORT.get(store, store),
            "slug": "".join(ch if ch.isalnum() else "-" for ch in store.lower()),
            "deal_count": int(len(group)),
            "strong_count": strong,
            "avg_score": round(avg_score),
            "verdict": _verdict(avg_score, strong),
            "top_categories": cats,
        })
    stores.sort(key=lambda s: (-s["strong_count"], -s["avg_score"], s["name"]))

    categories = []
    counts = df["display_category"].value_counts()
    for cat in CATEGORY_ORDER:
        if cat in counts.index:
            categories.append({"name": cat, "count": int(counts[cat])})
    for cat, n in counts.items():
        if cat not in CATEGORY_ORDER:
            categories.append({"name": str(cat), "count": int(n)})

    food_deals = [d for d in deals if d["category"] in FOOD_CATEGORIES]
    top_pool = food_deals if len(food_deals) >= 8 else deals
    # Sobeys and Safeway run one flyer, as do Superstore and No Frills, so the
    # same deal used to take two of the eight slots. Collapse within a parent
    # company only: Co-op at the same price is a real alternative, not a repeat.
    best: dict = {}
    order: list = []
    for deal in top_pool:
        key = (
            PARENT_COMPANY.get(deal["store"], deal["store"]),
            " ".join(deal["item"].lower().split()),
        )
        existing = best.get(key)
        if existing is None:
            best[key] = dict(deal, _also=[])
            order.append(key)
            continue
        candidate = dict(deal, _also=[])
        keep, drop = (
            (candidate, existing) if candidate["price"] < existing["price"] else (existing, candidate)
        )
        keep["_also"] = list(
            dict.fromkeys(keep["_also"] + drop["_also"] + [drop["store_short"]])
        )
        best[key] = keep

    top_deals = []
    for key in order:
        deal = best[key]
        # A second listing at the same store is not another place to shop.
        others = [x for x in deal.pop("_also", []) if x != deal["store_short"]]
        deal["also_at"] = ", ".join(others)
        top_deals.append(deal)
        if len(top_deals) == 8:
            break

    strong_total = int((df["deal_score"] >= STRONG_SCORE).sum())
    lowest_total = int(df["is_lowest_historical"].fillna(False).astype(bool).sum()) if "is_lowest_historical" in df.columns else 0
    model_share = None
    if "ai_confidence" in df.columns and len(df):
        model_share = round(100 * float((df["ai_confidence"].astype(str) != "statistical").mean()))

    best_store = stores[0]["short"] if stores else ""
    strong_food = df[(df["deal_score"] >= STRONG_SCORE) & df["display_category"].isin(FOOD_CATEGORIES)]
    best_cat = str(strong_food["display_category"].value_counts().index[0]) if len(strong_food) else ""
    weak = [s["short"] for s in stores if s["verdict"] == "Weak"]
    lede = (
        f"{strong_total:,} of {len(df):,} flyer prices are genuinely worth a trip this week."
        + (f" {best_store} has the strongest flyer" if best_store else "")
        + (f", and {best_cat.lower()} is the category to stock up on." if best_cat else ".")
        + (f" {', '.join(weak)} is a skip." if len(weak) == 1 else (f" {', '.join(weak)} are skips." if weak else ""))
    )

    telegram = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    telegram_url = f"https://t.me/{telegram[1:]}" if telegram.startswith("@") else ""

    latest = latest or {}
    return {
        "base_url": base_url,
        "week_ending": latest.get("week_ending") or modal_until or datetime.now().strftime("%Y-%m-%d"),
        "valid_from": modal_from,
        "generated_at": latest.get("generated_at") or datetime.now().isoformat(timespec="minutes"),
        "lede": lede,
        "stats": {
            "total": int(len(df)),
            "strong": strong_total,
            "lowest_ever": lowest_total,
            "stores": len(stores),
            "best_store": best_store,
            "best_category": best_cat,
            "model_share": model_share,
        },
        "top_deals": top_deals,
        "stores": stores,
        "categories": categories,
        "deals": deals,
        "reports": {
            "store": latest.get("store_report") or "",
            "category": latest.get("category_report") or "",
            "facebook": latest.get("facebook_post") or "",
        },
        "links": {
            "telegram": telegram_url,
            "facebook": os.getenv("FACEBOOK_GROUP_URL", "").strip(),
            "dashboard": os.getenv("DASHBOARD_APP_URL", "").strip(),
        },
    }


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
_CSS = r"""
:root{--paper:#f6efe3;--paper-2:#efe4d1;--ink:#1d1a16;--ink-2:#5b544a;--rule:#d9ccb4;--tomato:#d5372b;--leaf:#2f6b3a;--butter:#f2c14e;--card:#fffaf1;--focus:#1d1a16}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.45}
body::before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.35;mix-blend-mode:multiply;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 .08 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
a{color:inherit}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px 80px}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace}
.serif{font-family:Fraunces,Georgia,serif}
.mast{display:grid;grid-template-columns:1fr auto;align-items:end;gap:16px;padding:24px 0 14px;border-bottom:3px double var(--ink)}
.kicker{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-2)}
.brand{font-family:Fraunces,Georgia,serif;font-variation-settings:"SOFT" 40,"opsz" 144;font-weight:900;font-size:clamp(34px,7vw,68px);line-height:.94;letter-spacing:-.02em;margin:6px 0 0}
.brand em{font-style:italic;font-weight:400;color:var(--tomato)}
.week{text-align:right;font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:var(--ink-2);line-height:1.5}
.week b{display:block;font-family:Fraunces,Georgia,serif;font-size:26px;color:var(--ink);font-weight:700}
.strip{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--rule)}
.strip div{padding:14px 10px 12px;border-right:1px solid var(--rule)}
.strip div:last-child{border-right:0}
.strip .n{font-family:Fraunces,Georgia,serif;font-weight:800;font-size:28px;line-height:1;letter-spacing:-.02em}
.strip .l{font-size:12px;color:var(--ink-2);margin-top:4px}
.hero{display:grid;grid-template-columns:1.05fr 1fr;gap:28px;padding:28px 0 26px;border-bottom:1px solid var(--rule);align-items:start}
.hero h2{font-family:Fraunces,Georgia,serif;font-weight:700;font-size:clamp(26px,4.2vw,40px);line-height:1.05;letter-spacing:-.02em;margin:0 0 14px}
.hero p{font-size:16px;color:var(--ink-2);margin:0 0 18px;max-width:52ch}
.cta{display:inline-flex;align-items:center;gap:8px;background:var(--ink);color:var(--paper);text-decoration:none;padding:11px 16px;border-radius:999px;font-weight:600;font-size:14px;margin:0 8px 8px 0}
.cta.alt{background:transparent;color:var(--ink);border:1.5px solid var(--ink)}
.cta:hover{background:var(--tomato);color:#fff;border-color:var(--tomato)}
.board{background:var(--card);border:1.5px solid var(--ink);border-radius:10px;box-shadow:6px 6px 0 var(--ink);padding:12px 14px 6px}
.board h3{margin:0 0 4px;font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-2);display:flex;justify-content:space-between}
.brow{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:9px 0;border-top:1px dashed var(--rule);text-decoration:none}
.brow:first-of-type{border-top:0}
.brow .p{font-family:Fraunces,Georgia,serif;font-weight:900;font-size:26px;letter-spacing:-.03em;color:var(--tomato);min-width:84px;line-height:1}
.brow .nm{display:block;font-weight:600;font-size:14px;line-height:1.2}
.brow .sub{display:block;font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-2);margin-top:2px}
.brow .drop{font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:12px;background:var(--butter);border:1.5px solid var(--ink);border-radius:999px;padding:3px 8px;transform:rotate(-4deg)}
.brow:hover .nm{color:var(--tomato)}
.sec{margin:34px 0 10px;display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap}
.sec h3{font-family:Fraunces,Georgia,serif;font-weight:800;font-size:26px;letter-spacing:-.02em;margin:0}
.sec .sub{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-2)}
.tools{position:sticky;top:0;z-index:5;background:var(--paper);padding:10px 0 8px;border-bottom:1px solid var(--rule);display:grid;gap:8px}
.tools input[type=search]{width:100%;font:inherit;font-size:15px;padding:11px 14px;border:1.5px solid var(--ink);border-radius:10px;background:var(--card);color:var(--ink)}
.chips{display:flex;gap:6px;overflow:auto;padding:2px 0;scrollbar-width:none}
.chips button{white-space:nowrap;font:inherit;font-size:12.5px;font-weight:500;border:1px solid var(--ink);border-radius:999px;padding:5px 11px;background:var(--card);color:var(--ink);cursor:pointer}
.chips button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.chips .cnt{opacity:.55;font-family:"IBM Plex Mono",monospace;font-size:11px;margin-left:4px}
.status{font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--ink-2)}
.stores{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:14px}
.store{background:var(--card);border:1px solid var(--rule);border-top:4px solid var(--ink);padding:12px 14px 8px;border-radius:6px;min-width:0}
.store header{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px}
.store h4{font-family:Fraunces,Georgia,serif;font-weight:800;font-size:22px;margin:0;letter-spacing:-.01em}
.store .meta{font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-2)}
.verdict{font-family:"IBM Plex Mono",monospace;font-size:11px;padding:3px 8px;border-radius:4px;background:var(--paper-2);color:var(--ink-2);white-space:nowrap}
.verdict.Hot{background:var(--tomato);color:#fff}.verdict.Solid{background:var(--leaf);color:#fff}.verdict.Weak{background:var(--ink);color:var(--paper)}
.deal{border-top:1px dashed var(--rule)}
.deal summary{list-style:none;display:grid;grid-template-columns:74px 1fr auto;gap:10px;padding:9px 0;cursor:pointer;align-items:start}
.deal summary::-webkit-details-marker{display:none}
.deal .p{font-family:Fraunces,Georgia,serif;font-weight:900;font-size:21px;letter-spacing:-.03em;line-height:1}
.deal .u{display:block;font-family:"IBM Plex Mono",monospace;font-size:10px;color:var(--ink-2);font-weight:500;letter-spacing:0}
.deal .nm{display:block;font-weight:600;font-size:14px;line-height:1.25}
.deal .why1{display:block;font-size:12px;color:var(--ink-2);margin-top:2px}
.deal .cat{display:block;font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--leaf);margin-top:3px}
.score{font-family:"IBM Plex Mono",monospace;font-size:11px;font-weight:600;border:1px solid var(--rule);border-radius:4px;padding:2px 6px;color:var(--ink-2)}
.score.s80{background:var(--butter);border-color:var(--ink);color:var(--ink)}
.score.s90{background:var(--tomato);border-color:var(--tomato);color:#fff}
.deal .body{padding:0 0 12px;font-size:13px;color:var(--ink-2)}
.deal .body ul{margin:4px 0 8px;padding-left:18px}
.deal .body li{margin:2px 0}
.deal .body .kv{display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;font-family:"IBM Plex Mono",monospace;font-size:11.5px;margin:4px 0 8px}
.deal .body a{font-weight:600;color:var(--ink)}
.deal[data-hidden=true]{display:none}
.morebtn{display:block;width:100%;text-align:center;font:600 12.5px "IBM Plex Sans",sans-serif;padding:10px 0 4px;background:none;border:0;color:var(--ink-2);cursor:pointer}
.morebtn:hover{color:var(--tomato)}
.store[data-empty=true]{display:none}
.empty{display:none;padding:30px;text-align:center;color:var(--ink-2)}
.posts{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.post{background:var(--card);border:1px solid var(--rule);border-radius:6px;padding:14px 16px 16px;min-width:0}
.post h5{margin:0 0 8px;font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-2);display:flex;justify-content:space-between;align-items:center}
.post pre{white-space:pre-wrap;word-wrap:break-word;font:14px/1.55 "IBM Plex Sans",sans-serif;margin:0;max-height:440px;overflow:auto}
.copy{font:600 11px "IBM Plex Mono",monospace;background:var(--ink);color:var(--paper);border:0;border-radius:6px;padding:5px 9px;cursor:pointer}
footer{margin-top:44px;padding-top:16px;border-top:3px double var(--ink);display:flex;flex-wrap:wrap;gap:10px 22px;font-size:13px;color:var(--ink-2)}
footer a{font-weight:600;color:var(--ink)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
@media (max-width:760px){.mast{grid-template-columns:1fr}.week{text-align:left}.strip{grid-template-columns:repeat(2,1fr)}.strip div:nth-child(2){border-right:0}.strip div:nth-child(-n+2){border-bottom:1px solid var(--rule)}.hero{grid-template-columns:1fr}.posts{grid-template-columns:1fr}.brow .p{font-size:22px;min-width:72px}}
@media (prefers-reduced-motion:no-preference){.brow,.deal summary{transition:color .15s}}
"""

_JS = r"""
(function(){
  var data = JSON.parse(document.getElementById('deal-data').textContent);
  var state = {store:'', cat:'', strong:false, q:''};
  var rows = Array.prototype.slice.call(document.querySelectorAll('.deal'));
  rows.forEach(function(el){
    var sm = el.querySelector('summary');
    el.dataset.text = ((sm ? sm.textContent : '') + ' ' + el.dataset.store + ' ' + el.dataset.cat).toLowerCase();
  });
  var stores = Array.prototype.slice.call(document.querySelectorAll('.store'));
  var status = document.getElementById('status');
  var empty = document.getElementById('empty');
  var PREVIEW = 5;

  function norm(s){ return (s||'').toLowerCase(); }
  function matches(el){
    if (state.store && el.dataset.store !== state.store) return false;
    if (state.cat && el.dataset.cat !== state.cat) return false;
    if (state.strong && +el.dataset.score < 80) return false;
    if (state.q && norm(el.dataset.text).indexOf(state.q) === -1) return false;
    return true;
  }
  function apply(){
    var shown = 0;
    stores.forEach(function(st){
      var list = Array.prototype.slice.call(st.querySelectorAll('.deal'));
      var expanded = st.dataset.expanded === 'true';
      var filtering = !!(state.cat || state.strong || state.q);
      var visible = 0, total = 0;
      list.forEach(function(el){
        var ok = matches(el);
        if (ok) total++;
        var show = ok && (expanded || filtering || visible < PREVIEW);
        if (show) visible++;
        el.dataset.hidden = show ? 'false' : 'true';
      });
      shown += total;
      st.dataset.empty = total === 0 ? 'true' : 'false';
      var btn = st.querySelector('.morebtn');
      if (btn){
        var hiddenCount = total - visible;
        btn.hidden = (filtering || expanded) ? (expanded ? false : true) : hiddenCount <= 0;
        btn.textContent = expanded ? 'Show fewer' : ('Show all ' + total + ' ' + st.dataset.short + ' deals');
      }
    });
    empty.style.display = shown ? 'none' : 'block';
    var bits = [];
    if (state.store) bits.push(state.store);
    if (state.cat) bits.push(state.cat);
    if (state.strong) bits.push('worth a trip only');
    if (state.q) bits.push('"' + state.q + '"');
    status.textContent = shown.toLocaleString() + ' of ' + data.total.toLocaleString() + ' deals' + (bits.length ? ' · ' + bits.join(' · ') : '');
  }
  function bindChips(id, key){
    var box = document.getElementById(id);
    if (!box) return;
    box.addEventListener('click', function(e){
      var b = e.target.closest('button'); if (!b || b.id === 'strong-toggle') return;
      var v = b.dataset.value || '';
      state[key] = (state[key] === v) ? '' : v;
      Array.prototype.forEach.call(box.querySelectorAll('button'), function(x){ if (x.id === 'strong-toggle') return; x.setAttribute('aria-pressed', x.dataset.value === state[key] && state[key] !== '' ? 'true' : (x.dataset.value === '' && state[key] === '' ? 'true' : 'false')); });
      apply();
    });
  }
  bindChips('store-chips', 'store');
  bindChips('cat-chips', 'cat');
  var strong = document.getElementById('strong-toggle');
  strong.addEventListener('click', function(){ state.strong = !state.strong; strong.setAttribute('aria-pressed', state.strong ? 'true' : 'false'); apply(); });
  var q = document.getElementById('q');
  var t; q.addEventListener('input', function(){ clearTimeout(t); t = setTimeout(function(){ state.q = norm(q.value.trim()); apply(); }, 120); });
  stores.forEach(function(st){
    var btn = st.querySelector('.morebtn');
    if (btn) btn.addEventListener('click', function(){ st.dataset.expanded = st.dataset.expanded === 'true' ? 'false' : 'true'; apply(); if (st.dataset.expanded !== 'true') st.scrollIntoView({block:'start'}); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('.copy'), function(b){
    b.addEventListener('click', function(){
      var pre = document.getElementById(b.dataset.target);
      if (!pre) return;
      navigator.clipboard.writeText(pre.textContent).then(function(){ b.textContent = 'COPIED'; setTimeout(function(){ b.textContent = 'COPY'; }, 1500); });
    });
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-jump]'), function(a){
    a.addEventListener('click', function(e){ var v = a.dataset.jump; if (!v) return; e.preventDefault(); state.store = v; var box = document.getElementById('store-chips'); Array.prototype.forEach.call(box.querySelectorAll('button'), function(x){ x.setAttribute('aria-pressed', x.dataset.value === v ? 'true' : 'false'); }); apply(); document.getElementById('stores').scrollIntoView({block:'start'}); });
  });
  apply();
})();
"""


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _score_class(score: int) -> str:
    if score >= 90:
        return "score s90"
    if score >= 80:
        return "score s80"
    return "score"


def _render_deal(d: dict) -> str:
    why1 = escape(d["why"][0]) if d["why"] else (escape(d["cross_store"]) if d["cross_store"] else "")
    unit = f'<span class="u">{escape(d["unit"])}</span>' if d["unit"] else ""
    kv = []
    if d["avg"] is not None:
        kv.append(("Usual price", d.get("avg_label") or _money(d["avg"])))
    if d["pct_below_avg"] is not None:
        kv.append(("vs usual", f"{d['pct_below_avg']:+d}%".replace("+", "−") if d["pct_below_avg"] > 0 else f"{abs(d['pct_below_avg'])}% above"))
    if d["hist_count"]:
        kv.append(("Prices tracked", str(d["hist_count"])))
    if d["cross_store"]:
        kv.append(("This week", d["cross_store"]))
    if d["lowest"]:
        kv.append(("History", "lowest we've recorded"))
    if d["valid_until"]:
        kv.append(("Valid until", d["valid_until"] + (" (long-running flyer)" if d["long_flyer"] else "")))
    if d["confidence"]:
        kv.append(("Confidence", f"{d['confidence']}/100"))
    kv_html = "".join(f"<span>{escape(k)}</span><b>{escape(v)}</b>" for k, v in kv)
    why_html = "".join(f"<li>{escape(w)}</li>" for w in d["why"])
    return (
        f'<details class="deal" data-store="{escape(d["store"])}" data-cat="{escape(d["category"])}" '
        f'data-score="{d["score"]}">'
        f'<summary><span class="p">{escape(d["price_label"])}{unit}</span>'
        f'<span><span class="nm">{escape(d["item"])}</span>'
        f'<span class="why1">{why1}</span>'
        f'<span class="cat">{escape(d["category"])}{(" · " + escape(d["action"])) if d["action"] else ""}</span></span>'
        f'<span class="{_score_class(d["score"])}">{d["score"]}</span></summary>'
        f'<div class="body"><div class="kv">{kv_html}</div>'
        f'{("<ul>" + why_html + "</ul>") if why_html else ""}'
        f'<a href="{escape(d["url"])}">Price history & chart →</a></div></details>'
    )


def render_weekly_page(model: dict) -> str:
    m = model
    s = m["stats"]
    week = _pretty_date(m["week_ending"], with_year=True)
    window = f"{_pretty_date(m['valid_from'])} – {_pretty_date(m['week_ending'])}" if m.get("valid_from") else f"to {_pretty_date(m['week_ending'])}"
    gen = pd.to_datetime(m["generated_at"], errors="coerce")
    gen_text = gen.strftime("%a %b %d, %I:%M %p").replace(" 0", " ") if pd.notna(gen) else ""

    deals_by_store: dict[str, list] = {}
    for d in m["deals"]:
        deals_by_store.setdefault(d["store"], []).append(d)

    board = "".join(
        f'<a class="brow" href="{escape(d["url"])}"><span class="p">{escape(d["price_label"])}</span>'
        f'<span><span class="nm">{escape(d["item"])}</span><span class="sub">{escape(d["store_short"])}'
        f'{(" + " + escape(d["also_at"])) if d.get("also_at") else ""}'
        f'{(" · usually " + _money(d["avg"])) if d["avg"] else ""}{(" · " + escape(d["cross_store"])) if d["cross_store"] else ""}</span></span>'
        f'<span class="drop">{("−" + str(d["pct_below_avg"]) + "%") if d["pct_below_avg"] else ("score " + str(d["score"]))}</span></a>'
        for d in m["top_deals"]
    )

    store_chips = '<button data-value="" aria-pressed="true">All stores</button>' + "".join(
        f'<button data-value="{escape(st["name"])}" aria-pressed="false">{escape(st["short"])}<span class="cnt">{st["deal_count"]}</span></button>'
        for st in m["stores"]
    )
    cat_chips = '<button data-value="" aria-pressed="true">All categories</button>' + "".join(
        f'<button data-value="{escape(c["name"])}" aria-pressed="false">{escape(c["name"])}<span class="cnt">{c["count"]}</span></button>'
        for c in m["categories"]
    )

    store_cards = []
    for st in m["stores"]:
        rows = deals_by_store.get(st["name"], [])
        cats = ", ".join(st["top_categories"]) if st["top_categories"] else "no standout categories"
        store_cards.append(
            f'<article class="store" id="store-{st["slug"]}" data-short="{escape(st["short"])}" data-expanded="false">'
            f'<header><div><h4>{escape(st["short"])}</h4><div class="meta">{st["deal_count"]} deals · {st["strong_count"]} worth a trip · {escape(cats)}</div></div>'
            f'<span class="verdict {st["verdict"]}">{st["verdict"]}</span></header>'
            + "".join(_render_deal(d) for d in rows)
            + f'<button class="morebtn" type="button">Show all {len(rows)} {escape(st["short"])} deals</button></article>'
        )

    reports = m["reports"]
    posts = ""
    if reports["store"] or reports["category"] or reports["facebook"]:
        blocks = []
        if reports["store"]:
            blocks.append(f'<div class="post"><h5>By store <button class="copy" data-target="post-store" type="button">COPY</button></h5><pre id="post-store">{escape(reports["store"])}</pre></div>')
        if reports["category"]:
            blocks.append(f'<div class="post"><h5>By category <button class="copy" data-target="post-cat" type="button">COPY</button></h5><pre id="post-cat">{escape(reports["category"])}</pre></div>')
        if reports["facebook"]:
            blocks.append(f'<div class="post"><h5>Short version <button class="copy" data-target="post-fb" type="button">COPY</button></h5><pre id="post-fb">{escape(reports["facebook"])}</pre></div>')
        posts = ('<div class="sec"><h3>The write-ups</h3><span class="sub">read by store or by category · copy for sharing</span></div>'
                 f'<div class="posts">{"".join(blocks)}</div>')

    links = m["links"]
    footer_links = ""
    if links.get("telegram"):
        footer_links += f'<a href="{escape(links["telegram"])}">Get this on Telegram</a>'
    if links.get("facebook"):
        footer_links += f'<a href="{escape(links["facebook"])}">Facebook group</a>'
    if links.get("dashboard"):
        footer_links += f'<a href="{escape(links["dashboard"])}">Full dashboard</a>'

    model_note = ""
    payload = json.dumps({"week_ending": m["week_ending"], "total": len(m["deals"])}, ensure_ascii=False).replace("</", "<\\/")
    title = f"Calgary grocery deals · week ending {week}"
    description = m["lede"]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,300..900,0..100&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="mast">
    <div>
      <div class="kicker">Calgary Grocery Hub · weekly flyer digest</div>
      <h1 class="brand">This week's <em>real</em> deals.</h1>
    </div>
    <div class="week">Flyers valid<b>{escape(window)}</b>Updated {escape(gen_text)} · {s['stores']} stores{escape(model_note)}</div>
  </header>

  <section class="strip" aria-label="This week at a glance">
    <div><div class="n">{s['total']:,}</div><div class="l">deals scanned</div></div>
    <div><div class="n">{s['strong']:,}</div><div class="l">worth a trip (score 80+)</div></div>
    <div><div class="n">{escape(s['best_store'] or '—')}</div><div class="l">strongest store this week</div></div>
    <div><div class="n">{escape(s['best_category'] or '—')}</div><div class="l">best category to stock up</div></div>
  </section>

  <section class="hero">
    <div>
      <h2>{escape(m['lede'])}</h2>
      <p>Every price below was checked against up to six months of flyer history and against the other stores this week. Scores of 80+ are the ones worth changing your route for.</p>
      <a class="cta" href="#stores">Plan by store ↓</a>
      <a class="cta alt" href="#posts">Read the write-ups</a>
    </div>
    <div class="board" aria-label="Top of the board">
      <h3><span>Top of the board</span><span>tap for price history</span></h3>
      {board}
    </div>
  </section>

  <div class="sec" id="stores"><h3>Every deal, store by store</h3><span class="sub">tap a row for the evidence · tap the link for its price chart</span></div>
  <div class="tools">
    <input id="q" type="search" placeholder="Search 1,000+ deals: chicken, cheese, coffee…" aria-label="Search deals">
    <div class="chips" id="store-chips" role="group" aria-label="Filter by store">{store_chips}</div>
    <div class="chips" id="cat-chips" role="group" aria-label="Filter by category"><button id="strong-toggle" aria-pressed="false" type="button">★ Worth a trip only</button>{cat_chips}</div>
    <div class="status" id="status" aria-live="polite"></div>
  </div>
  <div class="stores">{"".join(store_cards)}</div>
  <div class="empty" id="empty">Nothing matches that filter. Try clearing the search or picking another category.</div>

  <div id="posts"></div>
  {posts}

  <footer>
    <span>Prices from public store flyers for T3M 1M9. Averages use up to six months of history. No affiliate links.</span>
    {footer_links}
  </footer>
</div>
<script id="deal-data" type="application/json">{payload}</script>
<script>{_JS}</script>
</body>
</html>"""
