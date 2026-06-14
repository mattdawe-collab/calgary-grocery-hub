from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.data import store

router = APIRouter()


def _money(value) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _plain(value, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return str(value)


def _split_bullets(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _stat_card(label: str, value: str) -> str:
    return f"""
      <div class="stat">
        <div class="stat-value">{escape(value)}</div>
        <div class="stat-label">{escape(label)}</div>
      </div>
    """


def render_deal_snapshot_html(payload: dict, dashboard_url: str = "/") -> str:
    deal = payload["deal"]
    stats = payload.get("stats", {})
    cross_store = payload.get("cross_store_prices", [])
    why = _split_bullets(deal.get("why_bullets"))

    item = _plain(deal.get("item"), "Deal")
    price = _money(deal.get("price"))
    store_name = _plain(deal.get("store"))
    category = _plain(deal.get("category"))
    action = _plain(deal.get("action_label"), "Deal")
    score = round(float(deal.get("deal_score") or 0))
    confidence = round(float(deal.get("confidence_score") or 0))
    unit = ""
    if deal.get("unit_price") is not None and deal.get("unit_type"):
        unit = f"{_money(deal.get('unit_price'))} {deal.get('unit_type')}"

    rank_line = ""
    rank = deal.get("cross_store_rank")
    count = deal.get("cross_store_count")
    if rank and count and count > 1:
        rank_line = f"#{int(rank)} of {int(count)} stores this week"

    cross_rows = ""
    if cross_store:
        cross_rows = "".join(
            f"<li>{escape(_plain(row.get('store')))}: {escape(_money(row.get('price')))}</li>"
            for row in cross_store[:5]
        )
    else:
        cross_rows = "<li>No same-item store comparison available.</li>"

    why_rows = "".join(f"<li>{escape(text)}</li>" for text in why[:4]) or "<li>No evidence bullets available.</li>"
    title = f"{item} - {price} at {store_name}"
    description = f"{action}. Score {score}, confidence {confidence}. {category}."

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta name="description" content="{escape(description)}">
  <style>
    body {{
      margin: 0;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8fafc;
      color: #0f172a;
    }}
    main {{
      max-width: 720px;
      margin: 0 auto;
      padding: 24px;
    }}
    .panel {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 22px;
      box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }}
    .kicker {{
      font-size: 13px;
      color: #2563eb;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
      line-height: 1.15;
    }}
    .price {{
      font-size: 34px;
      font-weight: 800;
      color: #15803d;
      margin-right: 10px;
    }}
    .store {{
      color: #475569;
      font-size: 16px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0;
    }}
    .pill {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 13px;
      font-weight: 600;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin: 18px 0;
    }}
    .stat {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 12px;
      text-align: center;
    }}
    .stat-value {{
      font-size: 18px;
      font-weight: 800;
    }}
    .stat-label {{
      font-size: 12px;
      color: #64748b;
      margin-top: 3px;
    }}
    h2 {{
      font-size: 15px;
      margin: 20px 0 8px;
      color: #334155;
    }}
    ul {{
      margin: 0;
      padding-left: 20px;
      color: #334155;
    }}
    li {{
      margin: 5px 0;
    }}
    .footer {{
      margin-top: 20px;
      color: #64748b;
      font-size: 13px;
    }}
    .footer a {{
      color: #2563eb;
      text-decoration: none;
      font-weight: 600;
    }}
    @media (max-width: 560px) {{
      main {{ padding: 14px; }}
      .panel {{ padding: 16px; border-radius: 10px; }}
      h1 {{ font-size: 23px; }}
      .price {{ font-size: 30px; display: block; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <div class="kicker">{escape(action)}</div>
      <h1>{escape(item)}</h1>
      <div>
        <span class="price">{escape(price)}</span>
        <span class="store">at {escape(store_name)}</span>
      </div>
      <div class="meta">
        <span class="pill">Score {score}</span>
        <span class="pill">Confidence {confidence}</span>
        <span class="pill">{escape(category)}</span>
        {f'<span class="pill">{escape(rank_line)}</span>' if rank_line else ''}
        {f'<span class="pill">{escape(unit)}</span>' if unit else ''}
      </div>
      <div class="stats">
        {_stat_card("Historical Low", _money(stats.get("historical_min")))}
        {_stat_card("Average", _money(stats.get("historical_avg")))}
        {_stat_card("Historical High", _money(stats.get("historical_max")))}
        {_stat_card("Times Seen", str(stats.get("historical_count") or 0))}
        {_stat_card("Percentile", f"{round(float(stats.get('price_percentile') or 0))}th" if stats.get("price_percentile") is not None else "N/A")}
        {_stat_card("Sales/Month", f"~{stats.get('sale_frequency_per_month')}x" if stats.get("sale_frequency_per_month") else "N/A")}
      </div>
      <h2>Why it made the list</h2>
      <ul>{why_rows}</ul>
      <h2>This week's store comparison</h2>
      <ul>{cross_rows}</ul>
      <div class="footer">
        Snapshot generated from Calgary Grocery Hub data.
        <a href="{escape(dashboard_url)}">Open dashboard</a>
      </div>
    </section>
  </main>
</body>
</html>"""


@router.get("/share/deals/{deal_id}", response_class=HTMLResponse)
def deal_snapshot(deal_id: int, request: Request):
    store.check_reload()
    payload = store.get_deal_history(deal_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return HTMLResponse(content=render_deal_snapshot_html(payload, str(request.base_url)))
